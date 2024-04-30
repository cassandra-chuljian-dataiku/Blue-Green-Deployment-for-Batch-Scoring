import dataiku
from dataiku.scenario import Scenario
import logging
import time

from blue_green_deployment import (get_project_var, set_project_var, get_logger, get_metric_from_mes, get_step_result)
logger = get_logger()

scenario = Scenario()

client = dataiku.api_client()
project_api = client.get_default_project()

### STEP 0 : Load and init variables ###
logger.debug('STEP 0 : Load and init variables')
project = dataiku.Project(dataiku.default_project_key())

BLUE_SM_ID = project.get_variables()["standard"]["BLUE_SM_ID"]
GREEN_SM_ID = project.get_variables()["standard"]["GREEN_SM_ID"]
BLUE_MES_ID = project.get_variables()["standard"]["BLUE_MES_ID"]
GREEND_MES_ID = project.get_variables()["standard"]["GREEN_MES_ID"]

CHALLENGER_MODEL = project.get_variables()["standard"]["CHALLENGER_MODEL"]
#CHALLENGER_SPLIT = project.get_variables()["standard"]["CHALLENGER_SPLIT"]
MODEL_STATUS = project.get_variables()["standard"]["MODEL_STATUS"]

CHAMPION_MODEL = "BLUE" if CHALLENGER_MODEL == "GREEN" else "GREEN"

champion_mes_id, challenger_mes_id  = (BLUE_MES_ID, GREEND_MES_ID) if CHALLENGER_MODEL == "GREEN" else (GREEND_MES_ID, BLUE_MES_ID)
#challenger_mes = project.get_model_evaluation_store(challenger_mes_id)
#champion_mes = project.get_model_evaluation_store(champion_mes_id)

challenger_model_id = None
champion_model_id = None
challenger_accepted = False

logger.debug(f"all_var start : {scenario.get_all_variables()}")

# check is there is an ongoing deployment
if MODEL_STATUS == "DEPLOYED":

    ### STEP 1 : Retrain the challenger model ###
    logger.debug('STEP 1 : Retrain the challenger model')

    #Fetch challenger model id
    if CHALLENGER_MODEL == "BLUE":
        challenger_sm_id, champion_sm_id  = (BLUE_SM_ID, GREEN_SM_ID)
    elif CHALLENGER_MODEL == "GREEN":
        challenger_sm_id, champion_sm_id  = (GREEN_SM_ID, BLUE_SM_ID)
    else:
        raise(f"CHALLENGER_MODEL {CHALLENGER_MODEL} not recognised, needs to be 'GREEN' or 'BLUE'")

    retrain_step_name = f"Retrain Challenger Model : {CHALLENGER_MODEL}"
    train_ret = scenario.train_model(model_id = challenger_sm_id,
                                    step_name = retrain_step_name,
                                    fail_fatal=False) # Turn to True to fail scenario on training fail.
    trained_model = train_ret.get_trained_model()
    
    # Check Retrain Step Outcome
    step_result = get_step_result(scenario, retrain_step_name)
    logger.debug (f"retraining step Result : {step_result}")
    step_outcome = step_result["outcome"]
    if step_outcome == "ERROR":
        logger.debug (f"training_outcome : {step_outcome}, DO SOMETHING")
    

    
    ### STEP 2 : Assess the initial performance of the challenger model compared to the champion model. ###
    logger.debug('STEP 2 : Assess the initial performance of the challenger model compared to the champion model.')

    ## EVALUATE using MES (on external evaluation dataset)
    
    # Evaluate the challenger & champion to compare.
    eval_challenger_step_name = "Run Challenger Evaluation & Checks"
    eval_challenger = scenario.run_scenario(
        scenario_id = f"{CHALLENGER_MODEL}_MES_AND_CHECKS",
        name=eval_challenger_step_name,
        asynchronous=True,
        fail_fatal=True)
    
    eval_champion_step_name = "Run Champion Evaluation & Checks"
    eval_champion = scenario.run_scenario(
        scenario_id = f"{CHAMPION_MODEL}_MES_AND_CHECKS",
        name=eval_champion_step_name,
        asynchronous=True,
        fail_fatal=True
    )

    while not eval_challenger.is_done():
        time.sleep(1)
    while not eval_champion.is_done():
        time.sleep(1)
           
    logger.debug("MES has run for Challenger and Champion models")     
          
    # Check status of MES checks for both challenger and champion
    step_result = get_step_result(scenario, eval_challenger_step_name)
    logger.debug (f"challenger eval step Result : {step_result}")
    step_outcome = step_result["outcome"]
    if step_outcome == "WARNING":
        logger.debug (f"challenger eval step outcome : {step_outcome}, DO SOMETHING")
        
    step_result = get_step_result(scenario, eval_champion_step_name)
    logger.debug (f"champion eval step Result : {step_result}")
    step_outcome = step_result["outcome"]
    if step_outcome == "WARNING":
        logger.debug (f"champion eval step outcome : {step_outcome}, DO SOMETHING")
        
    # Load F1 of challenger and champion on eval dataset (using eval store) to compare.
    challenger_eval_F1 = get_metric_from_mes(mes_id = challenger_mes_id, metric_type = "F1")
    logger.debug(f"challenger F1 from MES : {challenger_eval_F1}")
    
    champion_eval_F1 = get_metric_from_mes(mes_id = champion_mes_id, metric_type = "F1")
    logger.debug(f"champion F1 from MES : {champion_eval_F1}")

     
    ## EVALUATION using SM active version training metrics. 
    
    # Load F1 of challenger on training dataset (using saved model) to compare
    challenger_sm = dataiku.Model(challenger_sm_id)
    active_id = [v["versionId"] for v in challenger_sm.list_versions() if v["active"] == True][0]
    challenger_training_F1 = float(challenger_sm.get_version_metrics(active_id).metrics.get_metric_by_id("model_perf:F1")["lastValues"][0]["value"])
    logger.debug(f"Challenger F1 from training : {challenger_training_F1}")
     
    #champion_sm = dataiku.Model(champion_sm_id) # Not needed in Specifications.
    #active_id = [v["versionId"] for v in champion_sm.list_versions() if v["active"] == True][0]
    #champion_training_F1 = float(champion_sm.get_version_metrics(active_id).metrics.get_metric_by_id("model_perf:F1")["lastValues"][0]["value"])
    #logger.debug(f"champion F1 from training : {champion_training_F1}")
    
    ## EVALUATION using Dataset Metrics
    
    # Build R2 score on predicted price (Custom model Metric in Dataset) for Champion and Challenger (NOT required in the specs)
    build_champion_prices = scenario.build_dataset(
                        dataset_name = f"{CHAMPION_MODEL}_sm_eval_dataset_with_prices",
                        build_mode='RECURSIVE_BUILD',
                        step_name=f"Compute prices for the challenger model",
                        asynchronous=True
                    )
    build_challenger_prices = scenario.build_dataset(
                        dataset_name = f"{CHALLENGER_MODEL}_sm_eval_dataset_with_prices" ,
                        build_mode='RECURSIVE_BUILD',
                        step_name=f"Compute prices for the challenger model",
                        asynchronous=True
                    )
    while not build_champion_prices.is_done():
        time.sleep(1)
    while not build_challenger_prices.is_done():
        time.sleep(1)
    
    # Run metrics
    scenario.compute_dataset_metrics(
                        dataset_name = f"{CHAMPION_MODEL}_sm_eval_dataset_with_prices",
                        step_name="Run champion model custom metrics",
                        asynchronous=False,
                    )
    scenario.compute_dataset_metrics(
                        dataset_name = f"{CHALLENGER_MODEL}_sm_eval_dataset_with_prices",
                        step_name="Run challenger model custom metrics",
                        asynchronous=False,
                    )
   
    # Run checks on metrics (The checks status will automatically stop the deployment)
    champion_custom_eval_step_name = "Run champion model custom metrics"
    scenario.run_dataset_checks(
                        dataset_name = f"{CHAMPION_MODEL}_sm_eval_dataset_with_prices",
                        step_name=champion_custom_eval_step_name,
                        asynchronous=False,
                        fail_fatal=True,
                    )
    challenger_custom_eval_step_name = "Run challenger model custom metrics"
    scenario.run_dataset_checks(
                        dataset_name = f"{CHALLENGER_MODEL}_sm_eval_dataset_with_prices",
                        step_name=challenger_custom_eval_step_name,
                        asynchronous=False,
                        fail_fatal=True,)
    
    # Check R2 Checks for warnings for both Champion and Challenger model.
    step_result = get_step_result(scenario, champion_custom_eval_step_name) 
    
    logger.debug(f"champion custom eval metric check Result : {step_result}")
    step_outcome = step_result["outcome"]
    if step_outcome == "WARNING":
        logger.debug (f"champion custom eval metric check outcome : {step_outcome}, DO SOMETHING")
    
    step_result = get_step_result(scenario, challenger_custom_eval_step_name)
    logger.debug (f"challenger custom eval metric check Result : {step_result}")
    step_outcome = step_result["outcome"]
    if step_outcome == "WARNING":
        logger.debug (f"challenger custom eval metric check outcome : {step_outcome}, DO SOMETHING")
    
    
    # Load the R2 metrics for champion and challenger to compare
    challenger_r2_dataset = project_api.get_dataset(f"{CHALLENGER_MODEL}_sm_eval_dataset_with_prices")
    challenger_eval_r2 = challenger_r2_dataset.get_metric_history("python:R2:Custom Model Metrics")["lastValue"]["value"]
    logger.debug(f"challenger R2 en eval : {challenger_eval_r2}")
    
    champion_r2_dataset = project_api.get_dataset(f"{CHAMPION_MODEL}_sm_eval_dataset_with_prices")
    champion_eval_r2 = champion_r2_dataset.get_metric_history("python:R2:Custom Model Metrics")["lastValue"]["value"]
    logger.debug(f"Champion R2 en eval : {champion_eval_r2}")

    ### Step 3 : MODEL COMPARISON ASSESSMENT ###
    logger.debug("Step 3 : MODEL PERFORMANCE ASSESSMEMENT")
        
    if challenger_eval_F1 >= champion_eval_F1 and challenger_training_F1>0.8 and challenger_eval_r2 > 0.95:
        challenger_accepted = True
    challenger_accepted = True # TO REMOVE
    logger.debug(f"Challenger accepted : {challenger_accepted}")


    if challenger_accepted:
        ### STEP 4 : Set Model Deployment Status to "IN DEPLOYMENT" (IF MODEL PERFORMANCE IS ACCEPTED) ###
        logger.debug('STEP 3 : Set Model Deployment Status to "IN DEPLOYMENT"')
        
        scenario.set_project_variables(
            project_key=dataiku.default_project_key(),
            step_name="Update model deployment status",
            MODEL_STATUS = "IN DEPLOYMENT"
        )

        ### STEP 4 : Deploy the Challenger model for parallel testing (IF MODEL PERFORMANCE IS ACCEPTED) ###
        logger.debug('STEP 4 : Deploy the Challenger model for parallel testing')
        scenario.run_scenario(
            scenario_id = "UPDATE_CHALLENGER_DEPLOYMENT",
            project_key=dataiku.default_project_key(),
        )









