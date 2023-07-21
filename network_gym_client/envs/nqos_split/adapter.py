from network_gym_client.adapter import Adapter

import sys
from gymnasium import spaces
import numpy as np
import pandas as pd
import math

MIN_DATA_RATE = 0
MAX_DATA_RATE = 100

MIN_DELAY_MS = 0
MAX_DELAY_MS = 500

class Adapter(Adapter):
    """Nqos split env adapter

    Args:
        Adapter (Adapter): base class
    """
    def __init__(self):
        """Initialize the adapter
        """
        self.env = "nqos_split"
        self.action_max_value = 32
        super().__init__()

    def get_action_space(self):
        """Get action space for the nqos split env

        Returns:
            spaces: action spaces
        """
        if (self.env == self.config_json['gmasim_config']['env'] and self.config_json['rl_agent_config']['agent'] != "custom" and "GMA" ):
            return spaces.Box(low=0, high=1,
                                            shape=(int(self.config_json['gmasim_config']['num_users']),), dtype=np.float32)
        #This is for CleanRL custom
        elif (self.env == self.config_json['gmasim_config']['env'] and self.config_json['rl_agent_config']['agent'] == "custom"):
            #Define your own action space to match with output of actor network
            return spaces.Box(low=0, high=1,
                                            shape=(1,), dtype=np.float32)
        else:
            sys.exit("[ERROR] wrong environment or RL agent.")

    #consistent with the prepare_observation function.
    def get_observation_space(self):
        """Get the observation space for nqos split env

        Returns:
            spaces: observation spaces
        """
        num_features = 3
        num_users = int(self.config_json['gmasim_config']['num_users'])
        obs_space = None

        obs_space =  spaces.Box(low=0, high=1000,
                                            shape=(num_features,num_users), dtype=np.float32)

        return obs_space
    
    def prepare_observation(self, df_list):
        """Prepare observation for nqos split env.

        This function should be consistent with the get_observation_space.

        Args:
            df_list (list[pandas.dataframe]): network stats measurement

        Returns:
            spaces: observation spaces
        """

        df_phy_lte_max_rate = df_list[0]
        df_phy_wifi_max_rate = df_list[1]
        df_load = df_list[2]
        df_rate = df_list[3]
        df_split_ratio = df_list[6]
        df_ap_id = df_list[7]

        dict_wifi_split_ratio = self.df_split_ratio_to_dict(df_split_ratio, "Wi-Fi")

        #print("Wi-Fi Split Ratio:" + str(dict_wifi_split_ratio))
        if not self.wandb_log_info:
            self.wandb_log_info = dict_wifi_split_ratio
        else:
            self.wandb_log_info.update(dict_wifi_split_ratio)


        #check if the data frame is empty
        if len(df_phy_wifi_max_rate)> 0:
            dict_phy_wifi = self.df_wifi_to_dict(df_phy_wifi_max_rate, "Max-Wi-Fi")
            if not self.wandb_log_info:
                self.wandb_log_info = dict_phy_wifi
            else:
                self.wandb_log_info.update(dict_phy_wifi)
        
        if len(df_phy_lte_max_rate)> 0:
            dict_phy_lte = self.df_lte_to_dict(df_phy_lte_max_rate, "Max-LTE")
            if not self.wandb_log_info:
                self.wandb_log_info = dict_phy_lte
            else:
                self.wandb_log_info.update(dict_phy_lte)
        
        #use 3 features
        emptyFeatureArray = np.empty([self.config_json['gmasim_config']['num_users'],], dtype=int)
        emptyFeatureArray.fill(-1)
        observation = []


        #check if there are mepty features
        if len(df_phy_lte_max_rate)> 0:
            # observation = np.concatenate([observation, df_phy_lte_max_rate[:]["value"]])
            phy_lte_max_rate = df_phy_lte_max_rate[:]["value"]

        else:
            # observation = np.concatenate([observation, emptyFeatureArray])
            phy_lte_max_rate = emptyFeatureArray
        
        if len(df_phy_wifi_max_rate)> 0:
            # observation = np.concatenate([observation, df_phy_wifi_max_rate[:]["value"]])
            phy_wifi_max_rate = df_phy_wifi_max_rate[:]["value"]

        else:
            # observation = np.concatenate([observation, emptyFeatureArray])
            phy_wifi_max_rate = emptyFeatureArray

        df_rate = df_rate[df_rate['cid'] == 'All'].reset_index(drop=True) #keep the flow rate.

        # print(df_rate)
        # print(df_rate.shape)


        if len(df_rate)> 0:
            # observation = np.concatenate([observation, df_rate[:]["value"]])
            phy_df_rate = df_rate[:]["value"]

        else:
            # observation = np.concatenate([observation, emptyFeatureArray])
            phy_df_rate = emptyFeatureArray

        # observation = np.ones((3, 4))

        observation = np.vstack([phy_lte_max_rate, phy_wifi_max_rate, phy_df_rate])
        if (observation < 0).any():
            print("[WARNING] some feature returns empty measurement, e.g., -1")

        
        # add a check that the size of observation equals the prepared observation space.
        return observation

    def prepare_policy(self, action):
        """Prepare policy for the nqos split env

        Args:
            action (spaces): action from the RL agent

        Returns:
            json: network policy
        """

        # Subtract 1 from the action array
        subtracted_action = 1- action 
        # print(subtracted_action)

        # Stack the subtracted and original action arrays
        stacked_action = np.vstack((action, subtracted_action))

        # Scale the subtracted action to the range [0, self.action_max_value]
        scaled_stacked_action= np.interp(stacked_action, (0, 1), (0, self.action_max_value))


        # Round the scaled subtracted action to integers
        rounded_scaled_stacked_action = np.round(scaled_stacked_action).astype(int)

        print("action --> " + str(rounded_scaled_stacked_action))
        policy = []

        for user_id in range(self.config_json['gmasim_config']['num_users']):
            #wifi_ratio + lte_ratio = step size == self.action_max_value
            # wifi_ratio = 14 #place holder
            # lte_ratio = 18 #place holder
            policy.append({"cid":"Wi-Fi","user":int(user_id),"value":int(rounded_scaled_stacked_action[0][user_id])})#config wifi ratio for user: user_id
            policy.append({"cid":"LTE","user":int(user_id),"value":int(rounded_scaled_stacked_action[1][user_id])})#config lte ratio for user: user_id

        return policy

    def df_to_dict(self, df, description):
        """Dataframe to dict covertor

        Args:
            df (pandas.dataframe): data
            description (str): description for the data

        Returns:
            dict: data dict
        """
        df_cp = df.copy()
        df_cp['user'] = df_cp['user'].map(lambda u: f'UE{u}_'+description)
        # Set the index to the 'user' column
        df_cp = df_cp.set_index('user')
        # Convert the DataFrame to a dictionary
        data = df_cp['value'].to_dict()
        return data

    def df_lte_to_dict(self, df, description):
        """LTE dataframe to dict covertor

        Args:
            df (pandas.dataframe): LTE data
            description (str): description for the data

        Returns:
            dict: data dict
        """
        df_cp = df.copy()
        df_cp['user'] = df_cp['user'].map(lambda u: f'UE{u}_'+description)
        # Set the index to the 'user' column
        df_cp = df_cp.set_index('user')
        # Convert the DataFrame to a dictionary
        data = df_cp['value'].to_dict()
        data["LTE_avg_rate"] = df_cp[:]['value'].mean()
        data["LTE_total"] = df_cp['value'].sum()
        return data

    def df_split_ratio_to_dict(self, df, cid):
        """Split ratio dataframe to dict convertor

        Args:
            df (pandas.dataframe): data
            cid (pandas.dataframe): connection ID

        Returns:
            dict: data dict
        """
        df_cp = df.copy()
        df_cp = df_cp[df_cp['cid'] == cid].reset_index(drop=True)
        df_cp['user'] = df_cp['user'].map(lambda u: f'UE{u}_{cid}_TSU')
        # Set the index to the 'user' column
        df_cp = df_cp.set_index('user')
        # Convert the DataFrame to a dictionary
        df_cp['value'] = df_cp['value']/self.action_max_value
        data = df_cp['value'].to_dict()
        return data

    def df_wifi_to_dict(self, df, description):
        """Wi-Fi dataframe to dict

        Args:
            df (pandas.dataframe): input data for Wi-Fi
            description (str): description

        Returns:
            dict: data dict
        """
        df_cp = df.copy()
        df_cp['user'] = df_cp['user'].map(lambda u: f'UE{u}_'+description)
        # Set the index to the 'user' column
        df_cp = df_cp.set_index('user')
        # Convert the DataFrame to a dictionary
        data = df_cp['value'].to_dict()
        data["WiFI_avg_rate"] = df_cp['value'].mean()
        data["WiFI_total"] = df_cp['value'].sum()
        return data

    def prepare_reward(self, df_list):
        """Prepare reward for the nqos split env

        Args:
            df_list (list[pandas.dataframe]): network stats

        Returns:
            spaces: reward spaces
        """

        df_load = df_list[2]
        df_rate = df_list[3]
        df_qos_rate = df_list[4]
        df_owd = df_list[5]

        #Convert dataframe of Txrate state to python dict
        df_rate = df_rate[df_rate['cid'] == 'All'].reset_index(drop=True) #keep the flow rate.
        dict_rate = self.df_to_dict(df_rate, 'rate')
        dict_rate["sum_rate"] = df_rate[:]["value"].sum()

        df_qos_rate_all = df_qos_rate[df_qos_rate['cid'] == 'All'].reset_index(drop=True)
        df_qos_rate_wifi = df_qos_rate[df_qos_rate['cid'] == 'Wi-Fi'].reset_index(drop=True)
        dict_qos_rate_all = self.df_to_dict(df_qos_rate_all, 'qos_rate')
        dict_qos_rate_all["sum_qos_rate"] = df_qos_rate_all[:]["value"].sum()

        dict_qos_rate_wifi = self.df_to_dict(df_qos_rate_wifi, 'wifi_qos_rate')
        dict_qos_rate_wifi["sum_wifi_qos_rate"] = df_qos_rate_wifi[:]["value"].sum()

        df_owd_fill = df_owd[df_owd['cid'] == 'All'].reset_index(drop=True)

        df_owd_fill = df_owd_fill[["user", "value"]].copy()
        df_owd_fill["value"] = df_owd_fill["value"].replace(0, 1)#change 0 delay to 1 for plotting
        df_owd_fill.index = df_owd_fill['user']
        df_owd_fill = df_owd_fill.reindex(np.arange(0, self.config_json['gmasim_config']['num_users'])).fillna(df_owd_fill["value"].max())#fill empty measurement with max delay
        df_owd_fill = df_owd_fill[["value"]].reset_index()
        dict_owd = self.df_to_dict(df_owd_fill, 'owd')

        df_dict = self.df_to_dict(df_load, 'tx_rate')
        df_dict["sum_tx_rate"] = df_load[:]["value"].sum()

        # _ = self.calculate_delay_diff(df_owd)

        avg_delay = df_owd["value"].mean()
        max_delay = df_owd["value"].max()

        # Pivot the DataFrame to extract "Wi-Fi" and "LTE" values
        # df_pivot = df_owd.pivot_table(index="user", columns="cid", values="value", aggfunc="first")[["Wi-Fi", "LTE"]]

        # Rename the columns to "wi-fi" and "lte"
        # df_pivot.columns = ["wi-fi", "lte"]

        # Sort the index in ascending order
        # df_pivot.sort_index(inplace=True)

        #check reward type, TODO: add reward combination of delay and throughput from network util function
        reward = 0
        if self.config_json["rl_agent_config"]["reward_type"] =="delay":
            reward = self.delay_to_scale(avg_delay)
        elif self.config_json["rl_agent_config"]["reward_type"] =="throughput":
            reward = self.rescale_datarate(df_rate[:]["value"].mean())
        elif self.config_json["rl_agent_config"]["reward_type"] == "utility":
            reward = self.netowrk_util(df_rate[:]["value"].mean(), avg_delay)
        elif self.config_json["rl_agent_config"]["reward_type"] == "delay_diff":
            # reward = self.delay_to_scale(self.calculate_delay_diff(df_owd))
            reward = self.calculate_delay_diff(df_owd)
        else:
            sys.exit("[ERROR] reward type not supported yet")

        #self.wandb.log(df_dict)

        #self.wandb.log({"step": self.current_step, "reward": reward, "avg_delay": avg_delay, "max_delay": max_delay})
        if not self.wandb_log_info:
            self.wandb_log_info = df_dict
        else:
            self.wandb_log_info.update(df_dict)
        self.wandb_log_info.update(dict_rate)
        self.wandb_log_info.update(dict_qos_rate_all)
        self.wandb_log_info.update(dict_qos_rate_wifi)
        self.wandb_log_info.update(dict_owd)
        self.wandb_log_info.update({"reward": reward, "avg_delay": avg_delay, "max_delay": max_delay})

        return reward

    def netowrk_util(self, throughput, delay, alpha=0.5):
        """
        Calculates a network utility function based on throughput and delay, with a specified alpha value for balancing.
        
        Args:
        - throughput: a float representing the network throughput in bits per second
        - delay: a float representing the network delay in seconds
        - alpha: a float representing the alpha value for balancing (default is 0.5)
        
        Returns:
        - a float representing the alpha-balanced metric
        """
        # Calculate the logarithm of the delay in milliseconds
        log_delay = -10
        if delay>0:
            log_delay = math.log(delay)

        # Calculate the logarithm of the throughput in mb per second
        log_throughput = -10
        if throughput>0:
            log_throughput = math.log(throughput)

        #print("delay:"+str(delay) +" log(owd):"+str(log_delay) + " throughput:" + str(throughput)+ " log(throughput):" + str(log_throughput))
        
        # Calculate the alpha-balanced metric
        alpha_balanced_metric = alpha * log_throughput - (1 - alpha) * log_delay

        alpha_balanced_metric = np.clip(alpha_balanced_metric, -10, 10)
        
        return alpha_balanced_metric

    def rescale_datarate(self,data_rate):
        """Rescales a given reward to the range [-10, 10].


        Args:
            data_rate (pandas.dataframe): data rater per user

        Returns:
            double : resclaed reward
        """
        # we should not assume the max throughput is known!!
        rescaled_reward = ((data_rate - MIN_DATA_RATE) / (MAX_DATA_RATE - MIN_DATA_RATE)) * 20 - 10
        return rescaled_reward



    def calculate_delay_diff(self, df_owd):
        """Calculate the delay difference of two links

        Args:
            df_owd (pandas.dataframe): one-way delay measurements

        Returns:
            double: delay difference
        """

        # can you add a check what if Wi-Fi or LTE link does not have measurement....
        
        #print(qos_rate)
        df_pivot = df_owd.pivot_table(index="user", columns="cid", values="value", aggfunc="first")[["Wi-Fi", "LTE"]]
        # Rename the columns to "wi-fi" and "lte"
        df_pivot.columns = ["wi-fi", "lte"]
        # Compute the delay difference between 'Wi-Fi' and 'LTE' for each user
        delay_diffs = df_pivot['wi-fi'].subtract(df_pivot['lte'], axis=0)
        abs_delay_diffs = delay_diffs.abs()
        # print(abs_delay_diffs)
        local_reward = 1/abs_delay_diffs*100
        reward = abs_delay_diffs.mean()
        return local_reward


    #I don't like this function...
    def delay_to_scale(self, data):
        """Rescale the action from [low, high] to [-1, 1].(no need for symmetric action space)

        Args:
            data (numpy.ndarray): delay

        Returns:
            numpy.ndarray: scaled delay
        """
        

        # low, high = 0,220
        # return -10*(2.0 * ((data - low) / (high - low)) - 1.0)
        low, high = MIN_DELAY_MS, MAX_DELAY_MS
        norm = np.clip(data, low, high)

        norm = ((data - low) / (high - low)) * -20 + 10
        # norm = (-1*np.log(norm) + 3) * 2.5
        #norm = np.clip(norm, -10, 20)

        return norm