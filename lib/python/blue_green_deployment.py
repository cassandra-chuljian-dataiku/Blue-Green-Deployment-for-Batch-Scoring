import dataiku
import logging
from typing import Any, Union

def get_project_var(project_var: str) -> Any:
    client = dataiku.api_client()
    project_api = client.get_default_project()
    v = project_api.get_variables()
    var_value = v["standard"].get(project_var,None)
    return var_value

def set_project_var (project_var: str, 
                     value: Any) -> None:
    client = dataiku.api_client()
    project_api = client.get_default_project()
    v = project_api.get_variables()
    v["standard"][project_var] = value
    project_api.set_variables(v)
    
def get_step_result(scenario, step_name):
    scenario_var = scenario.get_all_variables()
    return scenario_var[f'stepResult_{step_name}']
    
def get_logger(logging_level = ""):
    """
    
    logging_level (String): Optional
    logging levels are : CRITICAL, ERROR, WARNING, INFO, DEBUG, NOTSET
    If no logging level is given, the project variable "logging_level" will be used.
    
    """
    logger = logging.getLogger()
    if logging_level == "":
        logging_level = dataiku.get_custom_variables()["logging_level"] 
    eval("logging." +logging_level)
    logger.setLevel(eval("logging." +logging_level))
    logging.info(f"logging level set to {logging.getLevelName(logging.root.level)}")
    return logger

def get_metric_from_mes(mes_id : str, metric_type : str):
    client = dataiku.api_client()
    project = client.get_default_project()
    mes = project.get_model_evaluation_store(mes_id)
    latest_eval = mes.get_latest_model_evaluation()
    metric = [metric for metric in latest_eval.get_metrics()["metrics"] if metric["metric"]["metricType"]== metric_type]
    if len(metric)==0:
        raise Exception(f"Metric {metric_type} doesn't exist")
    else:
        metric = metric[0]
        data_type = metric["lastValues"][0]["dataType"]
        value = metric["lastValues"][0]["value"]
        if data_type == "DOUBLE":
            return float (value)
        if data_type == "BIGINT":
            return int(value)
        if data_type == "BOOLEAN":
            return bool(value)
        return value
