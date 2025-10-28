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
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "llama-3.1-8b")  # Default: llama-3.1-8b

# Validate that API keys are loaded
if not ENTSOE_API_KEY:
    raise ValueError("ENTSOE_API_KEY not found. Copy .env.example to .env and add your API key.")
if not CEREBRAS_API_KEY:
    raise ValueError("CEREBRAS_API_KEY not found. Copy .env.example to .env and add your API key.")

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
