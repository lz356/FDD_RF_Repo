import os
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import mean_squared_error
from sklearn.feature_selection import SelectKBest, f_classif

class FDD_RF_Modeling():
    """
    parameters:
        weather: the weather under which the building is simulated. Select from
            'AK_Fairbanks', 'FL_Miami', 'KY_Louisville', 'MN_Duluth',
            'SAU_Riyadh', 'TN_Knoxville', 'VA_Richmond'. The default value is
            'TN_Knoxville' where FRP locates.
        labeling_methodology: define the labeling methodology for each data
            point. Select from 'Simple' and 'Energy_Difference'. 'Simple' means
            all data points simulated under one fault type are labeled as that
            fault type. 'Energy Difference' means data will be labeled as fault
            only when electricity or gas consumption is 5% different from
            baseline, otherwise it will be labeled as 'baseline'. The default
            value is 'Simple'.
        feature_selection_methodology: Select from 'None', 'Embedded' and
            'Filter'. 'None' means no feature selection applied. 'Embedded'
            means using Random Forest's embedded feature selection to pre-select
             features. 'Filter' means using ANOVA correlation to select high
             correlated features. The default value is 'None'.
        aggregate_n_runs: Time resolution of FDD models. n = 1 represents 15
            minutes time resolution, which is the highest time resolution. n = 4
             represents 60 minutes time resolution. n = 96 represents daily time
              resolution. The default value is 4.
        number_of_trees: number of trees in the random forest algorithm

    functions:
        CDDR_tot: classifier performance metrics. Details can be found here:
            https://www.osti.gov/biblio/1503166
        create_folder_structure: create folder structure for data and results
        inputs_output_generator: generate inputs based on result csv and
            weather data
        get_models: train or load trained machine learning models
        make_predictions: make predictions based on inputs for testing and model
        whole_process_only_training: whole process only for training
        whole_process_only_testing: whole process only for testing
        whole_process_training_and_testing: whole process for both
            training and testing

    """
    def __init__(self, weather = 'TN_Knoxville', labeling_methodolog = 'Simple',
     feature_selection_methodology = 'None', aggregate_n_runs = 4,
     number_of_trees = 20):
        self.weather = weather
        self.labeling_methodolog = labeling_methodolog
        self.feature_selection_methodology = feature_selection_methodology
        self.number_of_trees = number_of_trees
        self.aggregate_n_runs = aggregate_n_runs
        self.root_path = os.getcwd()

    def CDDR_tot(self, Real_label, Pred_label):
        CD, CP = 0, 0
        for i,j in zip(Real_label,Pred_label):
            if (i == j) & (i != ('baseline')):
                CD += 1
            if i != 'baseline':
                CP += 1
        CDDR_tot = CD / CP
        return CDDR_tot

    def create_folder_structure(self):
        print('Creating folder structure...')
        folders = ['models/', 'results/', 'data/']
        for folder in folders:
            if not os.path.exists(os.path.join(self.root_path, folder)):
                os.makedirs(os.path.join(self.root_path, folder))

    def inputs_output_generator(self, train_or_test):
        print(f'Generating inputs for {train_or_test}ing...')

        if train_or_test == 'train':
            # read and aggregate raw data
            data_file_name_list = os.listdir(f'data\\{self.weather}\\{self.weather}\\')
            meta_data_file_name = [x for x in data_file_name_list if '_sensors' not in x][0]
            simulation_data_file_list = [x for x in data_file_name_list if '_sensors' in x]
            meta_data = pd.read_csv(f'data\\{self.weather}\\{self.weather}\\{meta_data_file_name}')

            fault_inputs_output = pd.DataFrame([])

            for simulation_data_file_name in simulation_data_file_list:
                temp_raw_FDD_data = pd.read_csv(f'data\\{self.weather}\\{self.weather}\\{simulation_data_file_name}')
                temp_raw_FDD_data = temp_raw_FDD_data.groupby(temp_raw_FDD_data.index // (self.aggregate_n_runs)).mean().iloc[:,0:-8]
                temp_raw_FDD_data['label'] = meta_data.loc[meta_data.id == simulation_data_file_name[0:-12]].fault_type.values[0]
                fault_inputs_output = pd.concat([fault_inputs_output, temp_raw_FDD_data], axis = 0)

            fault_inputs_output = fault_inputs_output.reset_index(drop = True)

            # Calculating outputs based on labeling methodology
            if self.labeling_methodolog == 'Simple':
                self.output_train = fault_inputs_output.iloc[:,-1]
            elif self.labeling_methodolog == 'Energy_Difference':
                pd.set_option('mode.chained_assignment', None)
                electricity_gas_label_df = fault_inputs_output[['electricity_facility [W]', 'gas_facility [W]', 'label']]
                baseline_electricity = electricity_gas_label_df.loc[electricity_gas_label_df.label == 'baseline']['electricity_facility [W]']
                baseline_electricity_repeated = pd.concat([baseline_electricity]* int(len(electricity_gas_label_df) / len(baseline_electricity)), ignore_index=True)
                baseline_gas = electricity_gas_label_df.loc[electricity_gas_label_df.label == 'baseline']['gas_facility [W]']
                baseline_gas_repeated = pd.concat([baseline_gas]* int(len(electricity_gas_label_df) / len(baseline_gas)), ignore_index=True)
                electricity_gas_label_df['baseline_electricity_facility [W]'] = baseline_electricity_repeated
                electricity_gas_label_df['baseline_gas_facility [W]'] = baseline_gas_repeated
                electricity_gas_label_df['electricity_over_threshold'] = (abs(electricity_gas_label_df['electricity_facility [W]'] - electricity_gas_label_df['baseline_electricity_facility [W]']) / electricity_gas_label_df['baseline_electricity_facility [W]']) > 0.05
                electricity_gas_label_df['gas_over_threshold'] = (abs(electricity_gas_label_df['gas_facility [W]'] - electricity_gas_label_df['baseline_gas_facility [W]']) / electricity_gas_label_df['baseline_gas_facility [W]']) > 0.05
                electricity_gas_label_df['electricity_over_threshold_or_gas_over_threshold'] = [x or y for x,y in zip(electricity_gas_label_df['electricity_over_threshold'], electricity_gas_label_df['gas_over_threshold'])]
                electricity_gas_label_df['adjusted_label'] = electricity_gas_label_df['label'] * electricity_gas_label_df['electricity_over_threshold_or_gas_over_threshold']
                electricity_gas_label_df['adjusted_label'] = electricity_gas_label_df['adjusted_label'].replace('', 'baseline')
                self.output_train = electricity_gas_label_df['adjusted_label'].rename('label')
            else:
                raise Exception("Error! Enter either 'Simple' or 'Energy_Difference' for labeling_methodolog")

            # Calculating inputs based on feature selection methods
            if self.feature_selection_methodology == 'None':
                self.inputs_train = fault_inputs_output.iloc[:,0:-1]
                self.important_features = fault_inputs_output.iloc[0:2,0:-1].columns.tolist()
            elif self.feature_selection_methodology == 'Embedded':
                model_feature_selection = RandomForestClassifier(n_estimators = 50, random_state=42)
                model_feature_selection.fit(fault_inputs_output.iloc[:,0:-1],self.output_train)
                feature_importance_temp = pd.DataFrame([])
                feature_importance_temp.loc[:,'sensor_name'] = fault_inputs_output.iloc[:,0:-1].columns
                feature_importance_temp.loc[:,'importance'] = model_feature_selection.feature_importances_
                self.important_features = feature_importance_temp.sort_values(
                    by=['importance'], ascending = False).sensor_name.tolist()[0:40]
                self.inputs_train = fault_inputs_output[self.important_features]
            elif self.feature_selection_methodology == 'Filter':
                # Use ANOVA to find most correlated inputs
                select_k_best_classifier = SelectKBest(f_classif, k=40)
                select_k_best_classifier.fit_transform(fault_inputs_output.iloc[:,0:-1], self.output_train)
                self.important_features = select_k_best_classifier.get_support(indices=True)
                self.important_features = fault_inputs_output.iloc[0:2, self.important_features].columns.tolist()
                self.inputs_train = fault_inputs_output[self.important_features]
            # Another 'Systematic' feature selection method combining filter method and embedded method with time series feature extraction is not finished yet.
            # This method is introduced in https://www.sciencedirect.com/science/article/abs/pii/S0360132320307071
            else:
                raise Exception("Error! Enter either 'None', 'Embedded' or 'Filter' for feature_selection_methodology")

        elif train_or_test == 'test':
            # read and aggregate tesing data
            test_data_file_name_list = os.listdir(f'data\\testing_data\\')
            self.test_simulation_data_file_list = [x for x in test_data_file_name_list if '_sensors' in x]

            fault_inputs = pd.DataFrame([])

            for simulation_data_file_name in self.test_simulation_data_file_list:
                temp_raw_FDD_data = pd.read_csv(f'data\\{self.weather}\\{self.weather}\\{simulation_data_file_name}')
                temp_raw_FDD_data = temp_raw_FDD_data.groupby(temp_raw_FDD_data.index // (self.aggregate_n_runs)).mean().iloc[:,0:-8]
                fault_inputs = pd.concat([fault_inputs, temp_raw_FDD_data], axis = 0)

            fault_inputs = fault_inputs.reset_index(drop = True)
            self.inputs_test = fault_inputs[self.important_features]

        else:
            raise Exception("Error! Enter either 'train' or 'test' for train_or_test")

    def get_models(self, train_or_load_model):

        if train_or_load_model == 'train':
            print(f'Training Model...')

            FDD_model = RandomForestClassifier(n_estimators = self.number_of_trees, random_state=42)
            FDD_model.fit(self.inputs_train, self.output_train)
            # Calculate training accuracy
            self.output_train_predicted = FDD_model.predict(self.inputs_train)
            self.training_accuracy_CDDR = self.CDDR_tot(self.output_train, self.output_train_predicted)
            self.model = FDD_model
            pickle.dump(self.model, open(f'models/{self.weather}.sav', 'wb'))
            print(f'Training Model Completed! Training Accuracy (CDDRtotal) is : {self.training_accuracy_CDDR}')
            # Module to be finished: cross-validation performance

        elif train_or_load_model == 'load':
            print(f'Loading Model...')
            self.model = pickle.load(open(f'models/{self.weather}.sav', 'rb'))
            print('Loading Model Completed!')
        else:
            raise Exception ("Error! Enter either 'train' or 'load' for train_or_load_model")

    def make_predictions(self):
        self.output_test = self.model.predict(self.inputs_test)
        prediction_order = ''.join(self.test_simulation_data_file_list)
        pd.DataFrame(self.output_test, columns = ['output_test' + prediction_order]).to_csv(f'results/{self.weather}.csv', index = None)
        print('Make and saving predictions...')
        print('Whole Process Completed!')

    def whole_process_only_training(self):
        self.create_folder_structure()
        self.inputs_output_generator(train_or_test = 'train')
        self.get_models(train_or_load_model = 'train')

    def whole_process_training_and_testing(self):
        self.create_folder_structure()
        self.inputs_output_generator(train_or_test = 'train')
        self.get_models(train_or_load_model = 'train')
        self.inputs_output_generator(train_or_test = 'test')
        self.make_predictions()

    def whole_process_only_testing(self):
        self.create_folder_structure()
        self.get_models(train_or_load_model = 'load')
        self.inputs_output_generator(train_or_test = 'test')
        self.make_predictions()
