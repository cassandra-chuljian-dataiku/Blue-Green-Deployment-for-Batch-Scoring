import dataiku
from dataiku.scenario import Scenario
import logging
import time

from blue_green_deployment import (get_project_var, 
                                   set_project_var, 
                                   get_logger, 
                                   get_metric_from_mes,
                                   get_step_result)
logger = get_logger()
scenario = Scenario()

# Most granular check

### Step 0 : Init and Load Variables
client = dataiku.api_client()
project = client.get_default_project()

BLUE_SM_ID = project.get_variables()["standard"]["BLUE_SM_ID"]
GREEN_SM_ID = project.get_variables()["standard"]["GREEN_SM_ID"]
BLUE_MES_ID = project.get_variables()["standard"]["BLUE_MES_ID"]
GREEND_MES_ID = project.get_variables()["standard"]["GREEN_MES_ID"]

CHALLENGER_MODEL = project.get_variables()["standard"]["CHALLENGER_MODEL"]
CHALLENGER_SPLIT = project.get_variables()["standard"]["CHALLENGER_SPLIT"]
MODEL_STATUS = project.get_variables()["standard"]["MODEL_STATUS"]

challenger_accepted = False
data_drift = False
performance_drift = False

# Convert BLUE/GREEN to Champion/Challenger
CHAMPION_MODEL = "BLUE" if CHALLENGER_MODEL == "GREEN" else "GREEN"

champion_mes_id, challenger_mes_id  = (BLUE_MES_ID, GREEND_MES_ID) if CHALLENGER_MODEL == "GREEN" else (GREEND_MES_ID, BLUE_MES_ID)
challenger_mes = project.get_model_evaluation_store(challenger_mes_id)
champion_mes = project.get_model_evaluation_store(champion_mes_id)


### Check if model is IN DEPLOYMENT or DEPLOYED ###
if MODEL_STATUS == "IN DEPLOYMENT":
    logger.debug('Update ongoing deployment')
    
    ### NOT NEED IN SPECS (Left for reference): Run evaluation for champion and challenger models on save evaluation set. 
    
    #eval_challenger = scenario.run_scenario(
    #    scenario_id = f"{CHALLENGER_MODEL}_MES_AND_CHECKS",
    #    name="Run Challenger Evaluation & Checks",
    #    asynchronous=True
    #)
    #eval_champion = scenario.run_scenario(
    #    scenario_id = f"{CHAMPION_MODEL}_MES_AND_CHECKS",
    #    name="Run Champion Evaluation & Checks",
    #    asynchronous=True
    #)

    #while not eval_challenger.is_done():
    #    time.sleep(1)
    #while not eval_champion.is_done():
    #    time.sleep(1)
    #logger.debug("Challenger and Champion have been evaluated")

    
    ### STEP 1 : Check the R2/PPP/uptake overall for the Champion and Challenger on their respective split
    #logger.debug(" STEP 1 : Check the R2/PPP/uptake overall for the Champion and Challenger on their respective splits")
    
    # Compute R2,PPP & uptake champion and challenger on their respective split (Dataset Metrics)
    build_champion_split_metrics = scenario.build_dataset(
                        dataset_name = f"champion_predictions",
                        build_mode='RECURSIVE_BUILD',
                        step_name=f"Compute champion split performance dataset",
                        asynchronous=False
                    )
    build_challenger_split_metrics = scenario.build_dataset(
                        dataset_name = f"challenger_predictions" ,
                        build_mode='RECURSIVE_BUILD',
                        step_name=f"Compute challenger split performance dataset",
                        asynchronous=False
                    )
    
    # Run metrics
    scenario.compute_dataset_metrics(
                        dataset_name = f"champion_predictions",
                        step_name="Run champion model metrics",
                        asynchronous=False,
                    )
    scenario.compute_dataset_metrics(
                        dataset_name = f"challenger_predictions",
                        step_name="Run challenger model metrics",
                        asynchronous=False,
                    )
    
    # Run checks on metrics (The checks status will automatically stop the deployment)
    champion_eval_check_step_name = "Run champion model metric checks"
    scenario.run_dataset_checks(
                        dataset_name = f"champion_predictions",
                        step_name=champion_eval_check_step_name,
                        asynchronous=False,
                        fail_fatal=True,
                    )
    challenger_eval_check_step_name = "Run challenger model metrics checks"
    scenario.run_dataset_checks(
                        dataset_name = f"challenger_predictions",
                        step_name=challenger_eval_check_step_name,
                        asynchronous=False,
                        fail_fatal=True,
                    )
    
    # Check if metrics checks gave Status gave warnings.
    step_result = get_step_result(scenario, champion_eval_check_step_name)
    logger.debug (f"champion eval metric check Result : {step_result}")
    step_outcome = step_result["outcome"]
    if step_outcome == "WARNING":
        logger.debug (f"champion eval metric check outcome : {step_outcome}, DO SOMETHING")
        
    step_result = get_step_result(scenario, challenger_eval_check_step_name)
    logger.debug (f"challenger eval metric check Result : {step_result}")
    step_outcome = step_result["outcome"]
    if step_outcome == "WARNING":
        logger.debug (f"challenger eval metric check outcome : {step_outcome}, DO SOMETHING")
    
    
    ### Step 2 : Load and compare the performance metrics of Champion and Challenger on their respective splits
    logger.debug("Step 2 : Load and compare the performance metrics of Champion and Challenger on their respective splits")
    
    challenger_r2_dataset = project.get_dataset(f"challenger_predictions")
    challenger_r2 = challenger_r2_dataset.get_metric_history("python:R2:Custom Model Metrics")["lastValue"]["value"]
    challenger_ppp_overall = challenger_r2_dataset.get_metric_history("col_stats:MEAN:PPP_overall")["lastValue"]["value"]
    challenger_uptake_overall = challenger_r2_dataset.get_metric_history("col_stats:MEAN:uptake_overall")["lastValue"]["value"]
    logger.debug(f"challenger_r2 on split : {challenger_r2}")
    logger.debug(f"challenger_ppp_overall on split : {challenger_ppp_overall}")
    logger.debug(f"challenger_uptake_overall on split : {challenger_uptake_overall}")
    
    champion_r2_dataset = project.get_dataset(f"champion_predictions")
    champion_r2 = champion_r2_dataset.get_metric_history("python:R2:Custom Model Metrics")["lastValue"]["value"]
    champion_ppp_overall = champion_r2_dataset.get_metric_history("col_stats:MEAN:PPP_overall")["lastValue"]["value"]
    champion_uptake_overall = champion_r2_dataset.get_metric_history("col_stats:MEAN:uptake_overall")["lastValue"]["value"]
    logger.debug(f"champion_r2 on split : {champion_r2}")
    logger.debug(f"champion_ppp_overall on split : {champion_ppp_overall}")
    logger.debug(f"champion_uptake_overall on split : {champion_uptake_overall}")
  
    
    # MODEL PERFORMANCE ASSESSMENT
    if challenger_ppp_overall > champion_ppp_overall*0.99 and challenger_uptake_overall > champion_uptake_overall*0.99:
        challenger_accepted = True 
    logger.debug("challenger_accepted : {challenger_accepted}")

    ### Step 3 : Keep deployment update process OR revert to Champion.
    logger.debug("Step 3 : Keep deployment update process OR revert to Champion.")
    if challenger_accepted:
        # Keep deployment update
        scenario.run_scenario(
            scenario_id = "UPDATE_CHALLENGER_DEPLOYMENT",
            name="Update Deployment",
        )
    else:
        # Revert back to champion 100%
        logger.debug("challenger not accepted reverting back to champion")
        scenario.set_project_variables(
            project_key=dataiku.default_project_key(),
            step_name="Update split back to 100% Champion",
            CHALLENGER_SPLIT = 0
        )
        scenario.set_project_variables(
            project_key=dataiku.default_project_key(),
            step_name="Update model status to DEPLOYED",
            MODEL_STATUS = "DEPLOYED"
        )
        

elif MODEL_STATUS == "DEPLOYED": 
    logger.debug('Check status of deployed model')
    
    ### STEP 1 : Evaluate the Champion model and compute drift. ###
    logger.debug('Step 1 : Evaluate the Champion model and compute drift')

    champion_mes_name = "Run Champion Evaluation & Checks"
    scenario.run_scenario(
        scenario_id = f"{CHAMPION_MODEL}_MES_AND_CHECKS",
        name=champion_mes_name
    )
    
    # Check champion MES for WARNINGS
    step_result = get_step_result(scenario, champion_mes_name)
    logger.debug (f"champion MES Result : {step_result}")
    step_outcome = step_result["outcome"]
    if step_outcome == "WARNING":
        logger.debug (f"champion MES outcome : {step_outcome}, DO SOMETHING")
   

    ### STEP 2 : Check Performance and Data Drift ###
    logger.debug('Step 2 : Check Performance and Data Drift')
    
    # Load drift metrics
    #champion_data_drift = get_metric_from_mes(mes_id = champion_mes_id, metric_type = "DATA_DRIFT")
    #champion_data_drift_pvalue = get_metric_from_mes(mes_id = champion_mes_id, metric_type = "DATA_DRIFT_PVALUE")
    
    latest_eval = champion_mes.get_latest_model_evaluation()
    for metric in latest_eval.get_metrics()["metrics"]:
        
        if metric["metric"]["id"] == "check:CHECK:Value in range of AUC":
            performance_drift_status = metric["lastValues"][0]["value"]
            if performance_drift_status == "ERROR":
                performance_drift = True
                logger.debug("Performance Drift Detected")

        if metric["metric"]["id"] == "check:CHECK:Value in range of Data Drift p-value":
            data_drift_status = metric["lastValues"][0]["value"]
            if data_drift_status == "ERROR":
                data_drift = True
                logger.debug("Data Drift Detected")
    
    ### STEP 3 : Notify/Act on Drift detection. ###
    logger.debug('Step 3 : Notify on Drift detection.')
    
    if data_drift:
        sender = scenario.get_message_sender(channel_id = "email")
        sender.set_params(sender="dss@company.com", recipient=str(project.get_variables()["standard"]["emails"]))
        sender.send(subject=f"Data Drift detected for project {project.get_summary()['projectKey']} ", message="Please go have a look")
        
        #retrain_scenario = scenario.run_scenario(
        #scenario_id = f"RETRAIN_CHALLENGER",
        #name="Retrain Challenger on data drift detection")
    
    if performance_drift:
        sender = scenario.get_message_sender(channel_id = "email")
        sender.set_params(sender="dss@company.com", recipient=str(project.get_variables()["standard"]["emails"]))
        sender.send(subject=f"Performance Drift detected for project {project.get_summary()['projectKey']}", message="Please go have a look")
        
        #retrain_scenario = scenario.run_scenario(
        #scenario_id = f"RETRAIN_CHALLENGER",
        #name="Retrain Challenger on performance drift detection")
    
else:
    raise (f"MODEL_STATUS {MODEL_STATUS} is not a valid model status value")


    
    
    
    
    
