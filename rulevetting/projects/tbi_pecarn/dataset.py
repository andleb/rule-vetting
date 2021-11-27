from os.path import join as oj

import numpy as np
import os
import pandas as pd
from tqdm import tqdm
from typing import Dict

import rulevetting
import rulevetting.api.util
# TODO
from rulevetting.projects.iai_pecarn import helper
from rulevetting.templates.dataset import DatasetTemplate


class Dataset(DatasetTemplate):
    def clean_data(self, data_path: str = rulevetting.DATA_PATH, **kwargs) -> pd.DataFrame:

        # raw data path
        raw_data_path = oj(data_path, self.get_dataset_id(), 'raw')
        os.makedirs(raw_data_path, exist_ok=True)

        # raw data file names to be loaded and searched over
        # for tbi, we only have one file
        fnames = sorted([
            fname for fname in os.listdir(raw_data_path)
            if 'csv' in fname])

        # read raw data
        for fname in tqdm(fnames):
            df = pd.read_csv(oj(raw_data_path, fname))

        return df

    def preprocess_data(self, cleaned_data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        tbi_df = cleaned_data.copy()
        ################################
        # Step 1: Remove variables which have nothing to do with our problem (uncontroversial choices)
        ################################
        list1 = ['EmplType', 'Certification']
        list2 = ['InjuryMech']

        # grab all of the CT/Ind variables
        list3 = []
        for col in tbi_df.keys():
            if 'Ind' in col or 'CT' in col:
                list3.append(col)

        list4 = ['AgeTwoPlus', 'AgeInMonth']

        # grab all of the Finding variables
        list5 = ['Observed', 'EDDisposition']

        for col in tbi_df.keys():
            if 'Finding' in col:
                list5.append(col)

        total_rem = list1 + list2 + list3 + list4 + list5

        tbi_df_step1 = tbi_df.drop(total_rem, axis=1)
        ################################
        # Step 2: Remove variables with really high missingness (that we don't care about)
        ################################
        tbi_df_step2 = tbi_df_step1.drop(['Ethnicity', 'Dizzy'], axis=1)

        ################################
        # Step 3: Remove observations with GCS < 14
        ################################
        tbi_df_step3 = tbi_df_step2[tbi_df_step2['GCSGroup'] == 2]
        tbi_df_step3 = tbi_df_step3.drop(['GCSGroup'], axis=1)

        ################################
        # Step 4: Remove Missing Observations Among the Response Outcomes
        ################################
        tbi_df_step4 = tbi_df_step3.dropna(subset=['DeathTBI', 'Intub24Head', 'Neurosurgery', 'HospHead'])
        tbi_df_step4['PosIntFinal'].fillna(0, inplace=True)

        ################################
        # Step 5: Make a New Column ciTBI, without the hospitalization condition
        ################################
        sset = tbi_df_step4[['DeathTBI', 'Intub24Head', 'Neurosurgery']]
        new_outcome = np.zeros(len(sset))
        new_outcome[np.sum(np.array(sset), 1) > 0] = 1

        tbi_df_step5 = tbi_df_step4.assign(PosIntFinalNoHosp=new_outcome)



        # TODO

        # drop cols with vals missing this percent of the time
        df = cleaned_data.dropna(axis=1, thresh=(1 - kwargs['frac_missing_allowed']) * cleaned_data.shape[0])

        # impute missing values
        # fill in values for some vars from unknown -> None
        df.loc[df['AbdomenTender'].isin(['no', 'unknown']), 'AbdTenderDegree'] = 'None'

        # pandas impute missing values with median
        df = df.fillna(df.median())
        df.GCSScore = df.GCSScore.fillna(df.GCSScore.median())

        df['outcome'] = df[self.get_outcome_name()]

        return df

    def extract_features(self, preprocessed_data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        # TODO
        # add engineered featuures
        df = helper.derived_feats(preprocessed_data)

        # convert feats to dummy
        df = pd.get_dummies(df, dummy_na=True)  # treat na as a separate category

        # remove any col that is all 0s
        df = df.loc[:, (df != 0).any(axis=0)]

        # remove the _no columns
        if kwargs['drop_negative_columns']:
            df.drop([k for k in df.keys() if k.endswith('_no')], inplace=True)

        # narrow to good keys
        feat_names = [k for k in df.keys()  # features to use
                      if not 'iai' in k.lower()]
        base_feat_names = []
        base_feat_names += ['AbdDistention', 'AbdTenderDegree', 'AbdTrauma', 'AbdTrauma_or_SeatBeltSign',
                            'AbdomenPain', 'Costal', 'DecrBreathSound', 'DistractingPain',
                            'FemurFracture', 'GCSScore', 'Hypotension', 'LtCostalTender',
                            'MOI', 'RtCostalTender', 'SeatBeltSign', 'ThoracicTender',
                            'ThoracicTrauma', 'VomitWretch', 'Age', 'Sex']
        base_feat_names += self.get_meta_keys()
        feats = rulevetting.api.util.get_feat_names_from_base_feats(feat_names,
                                                                    base_feat_names=base_feat_names) + ['outcome']
        return df[feats]

    def get_outcome_name(self) -> str:
        return 'PosIntFinal'  # return the name of the outcome we are predicting

    def get_dataset_id(self) -> str:
        return 'tbi_pecarn'  # return the name of the dataset id

    def get_meta_keys(self) -> list:
        # TODO
        return []  # keys which are useful but not used for prediction

    def get_judgement_calls_dictionary(self) -> Dict[str, Dict[str, list]]:
        return {
            'clean_data': {},
            'preprocess_data': {
                # drop cols with vals missing this percent of the time
                'frac_missing_allowed': [0.05, 0.10],
            },
            'extract_features': {
                # whether to drop columns with suffix _no
                'drop_negative_columns': [False],  # default value comes first
            },
        }


if __name__ == '__main__':
    dset = Dataset()
    df_train, df_tune, df_test = dset.get_data(save_csvs=True, run_perturbations=True)
    print('successfuly processed data\nshapes:',
          df_train.shape, df_tune.shape, df_test.shape,
          '\nfeatures:', list(df_train.columns))