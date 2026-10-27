"""
Configuration for HEMS agent with cost optimization settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# API Configuration
# Keys are loaded from .env file (copy .env.example to .env and add your keys)

# ENTSO-E API (electricity prices)
ENTSOE_API_KEY = os.getenv("ENTSOE_API_KEY")
BIDDING_ZONE = os.getenv("BIDDING_ZONE", "AT")  # Default: Austria

# Cerebras API (LLM inference)
# B2G change: provider, key and model come from b2g.agents.llm_client (LLM_PROVIDER etc. in .env);
# with nothing set it is still Cerebras + llama-3.1-8b. Names kept so the original code is unchanged.
from b2g.agents.llm_client import LLMSettings
LLM_SETTINGS = LLMSettings.from_env()
CEREBRAS_API_KEY = LLM_SETTINGS.api_key
CEREBRAS_MODEL = LLM_SETTINGS.model

# Validate that API keys are loaded
# ENTSO-E is optional: tools.get_electricity_prices falls back to data/prices_sample.json (B2G change, see docs/DECISIONS.md)
if not ENTSOE_API_KEY:
    print("⚠ ENTSOE_API_KEY not set - using sample prices from data/prices_sample.json")
if not CEREBRAS_API_KEY:
    raise ValueError(f"No API key for LLM provider '{LLM_SETTINGS.provider}'. Copy .env.example to .env and add "
                     f"{LLM_SETTINGS.provider.upper()}_API_KEY (or CEREBRAS_API_KEY for the original setup).")

# Agent behavior settings
TEMPERATURE = 0.0  # Deterministic outputs for consistent scheduling decisions

# Cost optimization settings
COMPACT_TOOL_OUTPUTS = True  # Use compact format for tool responses

# Available appliances and their agent configurations
AVAILABLE_APPLIANCES = {
    "washing_machine": {
        "agent_file": "washing_machine_agent.md",
        "default_duration_minutes": 120,
        "power_rating_kw": 2.0,
        "default_deadline": None,
        "default_request": "Schedule for a 2-hour cycle. Optimize for lowest cost.",
        "control_type": "binary",  # Binary on/off control
        "api_config": {
            "enabled": False,  # Set to True when device API is configured
            "endpoint": "http://homeassistant.local:8123/api/services/switch/turn_on",
            "method": "POST",
            "headers": {
                "Authorization": "Bearer {HASS_TOKEN}",  # Replace with actual token
                "Content-Type": "application/json"
            },
            "payload_template": {
                "entity_id": "switch.washing_machine",
                "start_time": "{start_time}",  # HH:MM format
                "duration_minutes": "{duration_minutes}"
            }
        }
    },
    "dishwasher": {
        "agent_file": "dishwasher_agent.md",
        "default_duration_minutes": 90,
        "power_rating_kw": 1.8,
        "default_deadline": None,
        "default_request": "Schedule for a 90-minute cycle. Optimize for lowest cost.",
        "control_type": "binary",
        "api_config": {
            "enabled": False,
            "endpoint": "http://homeassistant.local:8123/api/services/switch/turn_on",
            "method": "POST",
            "headers": {
                "Authorization": "Bearer {HASS_TOKEN}",
                "Content-Type": "application/json"
            },
            "payload_template": {
                "entity_id": "switch.dishwasher",
                "start_time": "{start_time}",
                "duration_minutes": "{duration_minutes}"
            }
        }
    },
    "ev_charger": {
        "agent_file": "ev_charger_agent.md",
        "default_duration_minutes": 360,
        "power_rating_kw": 7.4,
        "default_deadline": None,  # Deadline set dynamically from calendar
        "default_request": "Charge EV for 6 hours. Optimize for lowest cost.",
        "control_type": "binary",
        "api_config": {
            "enabled": False,
            "endpoint": "http://homeassistant.local:8123/api/services/switch/turn_on",
            "method": "POST",
            "headers": {
                "Authorization": "Bearer {HASS_TOKEN}",
                "Content-Type": "application/json"
            },
            "payload_template": {
                "entity_id": "switch.ev_charger",
                "start_time": "{start_time}",
                "duration_minutes": "{duration_minutes}",
                "target_soc": 80,  # Target state of charge (%)
                "charging_rate_kw": "{power_rating_kw}"  # Charging power limit
            }
        }
    }
}
