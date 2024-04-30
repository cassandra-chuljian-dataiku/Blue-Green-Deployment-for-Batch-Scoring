import dataiku
from dataiku.scenario import Scenario
import logging

scenario = Scenario()


### STEP 0 : Load and set variables ###
client = dataiku.api_client()
project = client.get_default_project()

BLUE_SM_ID = project.get_variables()["standard"]["BLUE_SM_ID"]
GREEN_SM_ID = project.get_variables()["standard"]["GREEN_SM_ID"]
CHALLENGER_MODEL = project.get_variables()["standard"]["CHALLENGER_MODEL"]

CHALLENGER_SPLIT = project.get_variables()["standard"]["CHALLENGER_SPLIT"]
MODEL_STATUS = project.get_variables()["standard"]["MODEL_STATUS"]

if MODEL_STATUS == "IN DEPLOYMENT":
    ### STEP 1 : Update the challenger/champion split  ###
    if CHALLENGER_SPLIT == 0:
        scenario.set_project_variables(
            step_name="Move from 0% to 10% of challenger model predictions used",
            CHALLENGER_SPLIT = 10
        )

    elif CHALLENGER_SPLIT == 10:
        scenario.set_project_variables(
            step_name="Move from 10% to 50% of the challenger model predictions used",
            CHALLENGER_SPLIT = 50
        )

    elif CHALLENGER_SPLIT == 50:
        if CHALLENGER_MODEL == "BLUE":
            scenario.set_project_variables(
                step_name="Update Champion",
                CHALLENGER_MODEL = "GREEN"
            )
        elif CHALLENGER_MODEL == "GREEN":
            scenario.set_project_variables(
                step_name="Update Champion",
                CHALLENGER_MODEL = "BLUE"
            )
        
        else:
            raise(f"CHALLENGER_MODEL {CHALLENGER_MODEL} not recognised, needs to be 'GREEN' or 'BLUE'")

        scenario.set_project_variables(
            project_key=dataiku.default_project_key(),
            step_name="Update split to use 100% of the champion model",
            CHALLENGER_SPLIT = 0
        )

        scenario.set_project_variables(
            project_key=dataiku.default_project_key(),
            step_name="Update model deployment status",
            MODEL_STATUS = "DEPLOYED"
        )

    else:
        raise (f"CHALLENGER_SPLIT {CHALLENGER_SPLIT} is not a valid split value")
    
    
    

