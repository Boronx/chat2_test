"""
Author: Yongqi Zhao
Date Created: 2023-12-14
Copy Right: TU Graz FTG ADAS Group
Email: yongqi.zhao@tugraz.at
"""
import streamlit as st
import pandas as pd
from GUI.Web_Sidebar import *
from utils.helper_original_scenario import generate_xosc
import time
from GUI.Web_MainContent import *
import sympy as sp
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from utils.prompt_engineering import *
from NLP.Scenario_Description_Understand import *
from scenario_mining.activity_identification import *
from scenario_mining.scenario_identification import *
# from API.Call_API import *

# *****************************************************************************************************************************************
#### Start construct website
# Set the layout of the page
st.set_page_config(
    layout="wide"  # Use "wide" layout to increase the main content area width
)


### Sidebar
dataset_option, metric_option, metric_suboption, dataset_load, metric_threshold, CA_Input, target_value = sidebar()


## global variables
# how to make the ego and target trajectory into global variables: after preview, click extract
fictive_ego_list_sampled = []
fictive_target_dicts_sampled = {}

# Initialize session state as a dictionary for original scenario
if 'my_data' not in st.session_state:
    st.session_state.my_data = {
        'fictive_ego_list_sampled': [], # original ego state
        'fictive_target_dicts_sampled': {}, # original target state
        'fictive_ego_list_sampled_tune': [], # tuned ego state
        'fictive_target_dicts_sampled_tune': {}, # tuned target state
        'tracks': pd.DataFrame(), # uploaded dataset after downsampling
        'tracks_original': pd.DataFrame(), # upload dataset without downsampling
        'framerate': 0, # framerate
        'desired_scenario': []
    }

frame_rate = None
# Define frame rate according to dataset 
if dataset_option == "AD4CHE":
    frame_rate = 30
else:
    frame_rate = 25
st.session_state.my_data['framerate'] = frame_rate


### Main content area
st.markdown("<h1 style='text-align: center; font-weight:bold; font-family:comic sans ms; padding-top: 0rem;'>Chat2Scenario</h1>", unsafe_allow_html=True)
st.markdown("<h2 style='text-align: center; padding-top: 0rem;'>Scenario extraction from dataset through utilization of large language model</h2>", unsafe_allow_html=True)

if dataset_option == "highD" or dataset_option == "AD4CHE":
    ## Check if uploaded data are correct
    csv_format = None
    if dataset_load is not None:
        csv_format = check_upload_csv(dataset_load, dataset_option)
        if not csv_format:
            st.warning(":warning: Uploaded dataset format is **NOT correct**! Check **selected dataset option** or **uploaded csv file**!")     

    ## Scenario extraction
    st.subheader(":film_frames: Scenario extraction")

    col1, col2 = st.columns(2)

    # The first column
    with col1:
        # OpenAI API key
        my_key = st.text_input(label = ":key: Enter your OpenAI key:", help="Please ensure you have an OpenAI API account with credit. ChatGPT Plus subscription does not include API access.", type="password")
        # Dataset 
        if dataset_option is not None:
            st.write(f":white_check_mark: Selected dataset: **{dataset_option}**")
        else:
            st.write(":x: Dataset is not selected:")
        # Upload 
        if dataset_load is not None:
            st.write(":white_check_mark: Data has been uploaded:")
        else:
            st.write(":x: No CSV file uploaded.")
        # Metric 
        if metric_suboption is not None:
            if metric_suboption != "Self-define":
                st.write(f":white_check_mark: Selected metric: **{metric_suboption}**")
        else:
            st.write(":x: Metric is not selected:")
        # xosc or txt
        selected_opts = st.selectbox(":bookmark_tabs: Select desired format:", ['xosc', 'txt'])
        # output path
        output_path = st.text_input(label=":file_folder: Enter your download path:", help="Please copy your desired download path.")
        # scenario description using naturlistic language from user
        scenario_description = st.text_area(":bulb: Please describe your desired scenarios:", height=15,\
                                            placeholder="To be decided... ...")
        

    # The second column
    with col2:
        preview_col1, extract_col2 = st.columns(2)
        with preview_col1:
            preview_button = st.button(":eyes: Preview searched scenario")
        with extract_col2:
            extract_btn = st.button(":arrow_down: Extract original scenario")

        reminder_holder = st.empty()

        # Preview button
        if preview_button: 
            meet_preview = check_preview_condition(reminder_holder, dataset_load, metric_suboption, metric_threshold, my_key, scenario_description)
            if meet_preview and csv_format:
                tracks_original = pd.read_csv(dataset_load)    
                # Insert original csv in the global variable
                st.session_state.my_data['tracks_original'] = tracks_original
                # Calculate all vehicles' longitudinal and lateral activity
                reminder_holder.warning(':running: Start analyze the vehicle activity...')
                progress_bar = st.progress(0)
                longActDict, latActDict, interactIdDict = main_fcn_veh_activity(tracks_original, progress_bar)

                # Understand scenario using GPT
                reminder_holder.warning(':thinking_face: Start understand scenario using LLM...')
                key_label = get_scenario_classification_via_LLM(my_key, scenario_description, progress_bar)
                if key_label != None:
                    print('Response of the LLM:')
                    print(key_label)
                    # Search correspondong scenarios from dictionary based on the key labels
                    reminder_holder.warning(':mag: Start search desired scenarios...')
                    scenarioList = mainFunctionScenarioIdentification(tracks_original, key_label, latActDict, longActDict, interactIdDict, progress_bar)
                    print("The following scenarios are in the scenario pool:")
                    print(scenarioList)
                    
                    # Calculate the metric value for frames when the requirements can be met
                    reminder_holder.warning(f"{len(scenarioList)} scenarios are found. Start calculate metric values...")
                    indexProgress = 0
                    for scenario_i in scenarioList:
                        # Make progress bar based on current index
                        progress = int((indexProgress / len(scenarioList)) * 100)
                        progress_bar.progress(progress)
                        # Find ego and target data
                        curr_scenario = scenario_i 
                        egoId = curr_scenario[0]
                        targetIds = curr_scenario[1]
                        initialFrame = curr_scenario[2]
                        finalFrame = curr_scenario[3]
                        egoVehData, tgtVehsData = find_vehicle_data_within_start_end_frame(tracks_original, egoId, targetIds, initialFrame, finalFrame)
                        metric_value_res = calc_metric_value_for_desired_scenario_segment(egoVehData, tgtVehsData, reminder_holder, metric_option, \
                                        metric_suboption, CA_Input, tracks_original, st.session_state.my_data['framerate'], target_value)
                        # Compare the calculated metric value with predefined threshold
                        isScenario = if_scenario_within_threshold(metric_value_res, metric_threshold)
                        if isScenario:
                            if curr_scenario not in st.session_state.my_data['desired_scenario']:
                                st.session_state.my_data['desired_scenario'].append(curr_scenario)

                        # Update for last item
                        indexProgress += 1
                        if indexProgress == len(scenarioList):
                            progress_bar.progress(100)

                reminder_holder.write(st.session_state.my_data['desired_scenario'])


                ## Scenario visualization
                if len(st.session_state.my_data['desired_scenario']) != 0:
                    num_sce = len(st.session_state.my_data['desired_scenario'])
                    print(f"{num_sce} scenairos are found!")
                    # Data preparation
                    fictive_ego_list = []
                    fictive_tgt_dict = dict()
                    for sce_i in st.session_state.my_data['desired_scenario']:
                        # Get ego vehicle
                        egoId = sce_i[0]
                        egoVehData = tracks_original[(tracks_original['id'] == egoId)].reset_index(drop=True)
                        fictive_ego_list.append(egoVehData)

                        # Get targets
                        tgtIds = sce_i[1]
                        tgtVehsData = []
                        for tgtId in tgtIds:
                            tgtVehData = tracks_original[(tracks_original['id'] == tgtId)].reset_index(drop=True)
                            tgtVehsData.append(tgtVehData)
                        
                        fictive_tgt_dict[egoId] = tgtVehsData
                    anmation_holder = st.empty()
                    preview_scenario(fictive_ego_list, fictive_tgt_dict, reminder_holder, anmation_holder, dataset_option)


        # Extract button
        if extract_btn:  
            extract = check_extract_condition(dataset_load, selected_opts, output_path, metric_threshold)
            if extract and csv_format:
                oriTracksDf = st.session_state.my_data['tracks_original']
                progress_bar_format = st.progress(0)
                # Convert scenario into OpenSCENARIO format
                # if selected_opts == "xosc":
                reminder_holder.warning("Start to generate OpenSCENARIO/text files...")
                # List: [[egoVehID, [tgtVehID,...], startFrame, endFrame],[],[]...]
                desired_scenarios = st.session_state.my_data['desired_scenario']
                xosc_index = 1
                for desired_scenario in desired_scenarios:
                    print(desired_scenario)
                    # progress bar
                    progress_num = int((xosc_index / len(desired_scenarios)) * 100)
                    progress_bar_format.progress(progress_num)
                    xosc_index += 1
                    if xosc_index == len(desired_scenarios):
                        progress_bar_format.progress(100)

                    # Get the ego vehicle information
                    egoVehID = desired_scenario[0]
                    egoVehTraj = oriTracksDf[oriTracksDf['id']==egoVehID].reset_index(drop=True)

                    # Find intersection of frames with the current target vehicle
                    common_frames = set(egoVehTraj['frame'])
                    tgtVehIDs = desired_scenario[1]
                    tgtVehTraj_common = []
                    for tgtVehID in tgtVehIDs:
                        tgtVehTraj = oriTracksDf[oriTracksDf['id'] == tgtVehID].reset_index(drop=True)
                        common_frames = common_frames.intersection(set(tgtVehTraj['frame']))
                        
                    # Now common_frames contains only frames that are common across all target vehicles and the ego vehicle
                    egoVehTraj_common = egoVehTraj[egoVehTraj['frame'].isin(common_frames)].copy().reset_index(drop=True)
                    # Ego vehicle trajectory post-processing: 1) add time; 2) move position; 3) flip y 
                    ego_time = (egoVehTraj_common['frame'] - egoVehTraj_common['frame'].iloc[0])/25
                    egoVehTraj_common['time'] = ego_time
                    egoVehTraj_common['x'] = egoVehTraj_common['x'] + 0.5*egoVehTraj_common['width']
                    egoVehTraj_common['y'] = egoVehTraj_common['y'] + 0.5*egoVehTraj_common['height']
                    egoVehTraj_common['y'] = -egoVehTraj_common['y']

                    tgtVehTrajs_common = []
                    # Get common trajectory data for all target vehicles
                    for tgtVehID in tgtVehIDs:
                        tgtVehTraj = oriTracksDf[oriTracksDf['id'] == tgtVehID]
                        tgtVehTraj_common = tgtVehTraj[tgtVehTraj['frame'].isin(common_frames)].copy().reset_index(drop=True)
                        # Target vehicle trajectory post-processing: 1) ad "time"; 2) move position; 3) flip y value  
                        tgt_time = (tgtVehTraj_common['frame'] - tgtVehTraj_common['frame'].iloc[0])/25
                        tgtVehTraj_common['time'] = tgt_time
                        tgtVehTraj_common['x'] = tgtVehTraj_common['x'] + 0.5*tgtVehTraj_common['width']
                        tgtVehTraj_common['y'] = tgtVehTraj_common['y'] + 0.5*tgtVehTraj_common['height']
                        tgtVehTraj_common['y'] = -tgtVehTraj_common['y']
                        tgtVehTrajs_common.append(tgtVehTraj_common)
                        

                    # Create input for "xosc_generation" and "IPG_CarMaker_text_generation"
                    sim_time = len(egoVehTraj_common)/25
                    output_path_xosc = output_path + '\\' + f'Chat2Scenario_xosc_{xosc_index}.xosc'
                    output_path_text = output_path + '\\' + f'Chat2Scenario_text_{xosc_index}.txt'
                    ego_track = egoVehTraj_common
                    tgt_tracks = tgtVehTrajs_common
                    

                    if selected_opts == "xosc":
                        xosc_generation(sim_time, output_path_xosc, ego_track, tgt_tracks)
                    # Generate IPG CarMaker text file
                    if selected_opts == "txt":
                        IPG_CarMaker_text_generation(output_path_text, ego_track, tgt_tracks)
                    
            
                reminder_holder.warning("All OpenSCENARIO/text files are successfully generated...")


    # ## Scenario variation: maybe better to combine with unknown & unsafe scenarios 
    # st.subheader(":clapper: Scenario variation")
    # col1_var, col2_var = st.columns(2)

    # # Set new value for metric
    # with col1_var:        
    #     st.warning(":man-lifting-weights: Coming soon...")

    # # Preview searched scenarios
    # with col2_var: 
    #     st.warning(":man-lifting-weights: Coming soon...")

# Compitable with more datasets is to be done
else:
    st.warning("Coming soon......")