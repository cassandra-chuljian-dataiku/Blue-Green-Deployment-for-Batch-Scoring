# This sample code helps you get started with the custom scenario API.
#For more details and samples, please see our Documentation
from dataiku.scenario import Scenario

# The Scenario object is the main handle from which you initiate steps
scenario = Scenario()

# A few example steps follow

# Building a dataset
scenario.build_dataset("customers_prepared", partitions="2015-01-03")

# Controlling the train of a dataset
train_ret = scenario.train_model("uSEkldfsm")
trained_model = train_ret.get_trained_model()
performance = trained_model.get_new_version_metrics().get_performance_values()
if performance["AUC"] > 0.85:
    trained_model.activate_new_version()

# Sending custom reports
sender = scenario.get_message_sender("mail-scenario", "local-mail") # A messaging channel
sender.set_params(sender="dss@company.com", recipient="data-scientists@company.com")

sender.send(subject="The scenario is doing well", message="All is good")
