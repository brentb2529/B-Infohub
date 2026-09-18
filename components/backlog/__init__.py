"""Flash-backed event log, so an outage does not erase the alarms."""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import time as time_
from esphome.const import CONF_ID, CONF_TIME_ID

CODEOWNERS = ["@bbensten"]
DEPENDENCIES = ["esp32"]

backlog_ns = cg.esphome_ns.namespace("backlog")
BacklogComponent = backlog_ns.class_("BacklogComponent", cg.Component)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(BacklogComponent),
        # Events are worth far less without a timestamp, so the clock source is
        # required rather than optional.
        cv.Required(CONF_TIME_ID): cv.use_id(time_.RealTimeClock),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_time(await cg.get_variable(config[CONF_TIME_ID])))
