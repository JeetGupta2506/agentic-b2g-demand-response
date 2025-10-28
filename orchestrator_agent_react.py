"""
LLM-Based HEMS Orchestrator Agent (ReAct Pattern)
Uses Reasoning-Action pattern for Cerebras (no tool calling support needed).
"""

import json
import re
import requests
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from tools import get_electricity_prices, call_appliance_agent, schedule_appliance, get_calendar_ev_constraint, calculate_window_sums
from config import CEREBRAS_API_KEY, CEREBRAS_MODEL, TEMPERATURE, AVAILABLE_APPLIANCES
from security import validate_and_prepare_input


class OrchestratorAgentReAct:
    """LLM-based orchestrator using ReAct pattern (reasoning + action)."""

    def __init__(self):
        """Initialize the ReAct orchestrator agent."""
        # Create enhanced system prompt with tool instructions
        self.system_prompt = self._create_system_prompt()

        self.api_key = CEREBRAS_API_KEY
        # Allow model override from environment (set by API)
        self.model = os.environ.get('CEREBRAS_MODEL_OVERRIDE', CEREBRAS_MODEL)
        self.temperature = TEMPERATURE
        self.base_url = "https://api.cerebras.ai/v1"

        print(f"[Orchestrator] Using model: {self.model}")

    def _create_system_prompt(self) -> str:
        """Create system prompt with ReAct pattern instructions."""
        # Load base orchestrator prompt
        prompt_path = Path(__file__).parent / "hems_orchestrator.md"
        with open(prompt_path, 'r') as f:
            base_prompt = f.read()

        # Add ReAct instructions
        react_instructions = """

## ReAct Pattern: Reasoning and Action

You will work through this task step-by-step using a Thought-Action-Observation cycle.

### Available Actions

You can perform these actions by outputting them in the specified format:

**Action: GET_PRICES**
Fetches electricity prices for the next 24 hours.
Format: `ACTION: GET_PRICES`

**Action: GET_CALENDAR_CONSTRAINT**
Fetches calendar events and extracts EV charging constraints.
Format: `ACTION: GET_CALENDAR_CONSTRAINT`

**Action: CALCULATE_WINDOW_SUMS**
Calculates sums for all consecutive price windows of a given size.
Format: `ACTION: CALCULATE_WINDOW_SUMS | window_size=<slots>`
Example: `ACTION: CALCULATE_WINDOW_SUMS | window_size=12` (for 3-hour windows)

**Action: CALL_AGENT**
Delegates to a specialist appliance agent.
Format: `ACTION: CALL_AGENT | agent_name=<name> | user_request=<request>`
Example: `ACTION: CALL_AGENT | agent_name=washing_machine_agent | user_request=Schedule for 2 hours, optimize for cost`

**Action: SCHEDULE**
Executes a schedule for an appliance.
Format: `ACTION: SCHEDULE | appliance_id=<id> | start_slot=<slot> | duration_slots=<slots> | reasoning=<why>`
Example: `ACTION: SCHEDULE | appliance_id=washing_machine | start_slot=14 | duration_slots=8 | reasoning=Optimal cost window`

**Action: FINISH**
Completes orchestration and presents final summary to user.
Format: `ACTION: FINISH | summary=<your summary message>`

### Your Workflow

**STEP 0: Scope Check (CRITICAL)**

Before doing ANYTHING else, verify the request is HEMS-related (Home Energy Management System). Valid requests involve:
- Scheduling appliances (washing machine, dishwasher, EV, heat pump)
- Optimizing energy consumption timing
- Checking electricity prices or price patterns
- Coordinating multiple flexible loads

If the request is completely unrelated (e.g., sports scores, general knowledge, unrelated tasks), immediately respond:
```
Thought: This request is outside my scope as a Home Energy Management System. I can only help with appliance scheduling and energy optimization.
ACTION: FINISH | summary=I can only help with home energy management tasks like scheduling appliances (washing machine, dishwasher, EV, heat pump) and optimizing energy consumption. Please ask me about scheduling your flexible loads or checking electricity prices.
```

**STEP 1+: Normal Workflow**

For valid HEMS requests, follow this cycle:

1. **Thought**: Explain what you're thinking and what action to take next
2. **Action**: Output EXACTLY ONE action in the format above, then STOP
3. **Observation**: The system will execute the action and show you the result
4. **Repeat** until you execute ACTION: FINISH

**Analytical Queries**: For price analysis, use CALCULATE_WINDOW_SUMS with appropriate window_size (e.g., 1 hour = 4 slots at 15min resolution). To identify expensive periods, use the MAXIMUM sum; to find cheap periods, use the MINIMUM sum.

**CRITICAL**: After outputting an ACTION, you MUST STOP and wait for the system to provide an Observation. DO NOT continue reasoning, DO NOT assume what the result will be, DO NOT output multiple actions in one response. Output ONE action, then wait.

### Required Workflow Order (CRITICAL)

**PRIORITY 3 FIX**: You MUST follow this exact sequence:

1. **First**: ACTION: GET_PRICES (always required)
2. **Second** (if EV involved): ACTION: GET_CALENDAR_CONSTRAINT (BEFORE calling any agents)
3. **Third**: ACTION: CALL_AGENT (for each appliance, one at a time)
4. **Fourth**: ACTION: SCHEDULE (after each agent recommendation)
5. **Final**: ACTION: FINISH (when all schedules executed)

**EV Detection**: If the user request mentions ANY of these keywords, EV is involved and you MUST call GET_CALENDAR_CONSTRAINT before calling ANY agents:
- "EV", "electric vehicle", "car", "charge", "charging", "vehicle", "all", "everything"

**Why this order matters**: Calendar constraints provide deadline information that agents need to optimize schedules. Calling it mid-workflow causes inefficiency and suboptimal schedules.

### Example

```
Thought: The user wants to schedule all flexible loads. First, I need to fetch electricity prices.
ACTION: GET_PRICES

[System executes and shows prices]

Thought: I have prices. The request mentions "all", which likely includes EV. I MUST check calendar constraints BEFORE calling any agents to ensure agents have complete constraint information.
ACTION: GET_CALENDAR_CONSTRAINT

[System shows calendar result]

Thought: Calendar shows user has work at 8am, so EV must be charged by 7:30am (slot 30). Now I can call each appliance agent with full constraint knowledge. Starting with washing machine...
ACTION: CALL_AGENT | agent_name=washing_machine_agent | user_request=Schedule for lowest cost

[System shows agent recommendation]

Thought: Washing machine agent recommends slot 50. Now I'll execute this schedule.
ACTION: SCHEDULE | appliance_id=washing_machine | start_slot=50 | duration_slots=8 | reasoning=Cost-optimized window

[Continue until all agents called and schedules executed]

Thought: All schedules executed successfully. Time to present final summary.
ACTION: FINISH | summary=I've optimized schedules for 4 appliances: ...
```

**IMPORTANT**: Always output actions in the exact format shown. The system will parse your output and execute the actions.
"""

        return base_prompt + react_instructions

    def _call_llm(self, messages: List[Dict[str, Any]]) -> str:
        """Call the LLM and return response text."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 4000,  # Allows comprehensive reasoning and detailed summaries
            "stream": False
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()

        result = response.json()
        return result['choices'][0]['message']['content'], result.get('usage', {})

    def _parse_action(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse action from LLM response with flexible matching."""
        # First, extract only the ACTION line to prevent "bleeding" from verbose models
        # Some models (like gpt-oss) continue writing after ACTION, contaminating parameters
        action_line_match = re.search(r'ACTION:.*', response, re.IGNORECASE)
        if action_line_match:
            # Get the full ACTION line, but stop at first newline or next "ACTION:"
            action_line = action_line_match.group(0)
            # Stop at newline to prevent multi-line contamination
            action_line = action_line.split('\n')[0]
            response = action_line

        # Try multiple patterns for robustness across different LLMs

        # Pattern 1: Standard format - ACTION: TYPE | params
        action_match = re.search(r'ACTION:\s*([A-Z_]+)(?:\s*\|\s*(.+?))?$', response, re.IGNORECASE)

        # Pattern 2: Allow underscores/hyphens in action name
        if not action_match:
            action_match = re.search(r'ACTION:\s*([A-Z_-]+)(?:\s*\|\s*(.+?))?$', response, re.IGNORECASE)

        # Pattern 3: Allow ACTION without colon (some models forget it)
        if not action_match:
            action_match = re.search(r'ACTION\s+([A-Z_]+)(?:\s*\|\s*(.+?))?$', response, re.IGNORECASE)

        if not action_match:
            return None

        action_type = action_match.group(1).upper().replace('-', '_').replace(' ', '_')
        action_params_str = action_match.group(2)

        action = {"type": action_type}

        # Parse parameters if present
        if action_params_str:
            # More robust parameter parsing
            params = {}
            # Split by | but handle potential issues
            parts = action_params_str.split('|')
            for param in parts:
                param = param.strip()
                if '=' in param:
                    key, value = param.split('=', 1)
                    # Clean key and value (remove quotes if present)
                    key = key.strip().strip('"\'')
                    value = value.strip().strip('"\'')

                    # Stop parsing if we encounter continuation markers (contamination from verbose models)
                    contamination_markers = ['ACTION:', 'Thought:', 'Observation:', 'FINISH', 'SCHEDULE', 'CALL_AGENT']
                    for marker in contamination_markers:
                        if marker in value:
                            value = value[:value.index(marker)].strip()
                            break

                    params[key] = value
            action["params"] = params

        return action

    def _execute_action(self, action: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Execute an action and return observation."""
        action_type = action["type"]
        params = action.get("params", {})

        if action_type == "GET_PRICES":
            print("\n   [Action] Fetching electricity prices...")
            # Check if cached prices should be used (for systematic evaluation)
            use_cached = os.environ.get('USE_CACHED_PRICES', 'false').lower() == 'true'
            prices_data = get_electricity_prices(use_cached_prices=use_cached)
            context["prices_data"] = prices_data
            return f"✓ Fetched {len(prices_data['prices'])} price points for {prices_data['date']}. Price range: {min(prices_data['prices']):.4f} - {max(prices_data['prices']):.4f} EUR/kWh. Prices stored in context."

        elif action_type == "GET_CALENDAR_CONSTRAINT":
            print("\n   [Action] Checking calendar for constraints...")
            constraint = get_calendar_ev_constraint()
            context["calendar_constraint"] = constraint
            if constraint:
                return f"✓ Calendar constraint found: Event '{constraint['event_title']}' at {constraint['event_time']}. EV deadline: {constraint['deadline_time']}. Reasoning: {constraint['reasoning']}"
            else:
                return "ℹ No calendar constraints found."

        elif action_type == "CALCULATE_WINDOW_SUMS":
            window_size = params.get("window_size")

            if not window_size:
                return "✗ Error: Missing window_size parameter"

            if "prices_data" not in context:
                return "✗ Error: Must call GET_PRICES before calculating window sums"

            try:
                window_size = int(window_size)
            except (ValueError, TypeError):
                return "✗ Error: window_size must be an integer"

            print(f"\n   [Action] Calculating window sums for {window_size} slots...")
            result = calculate_window_sums(
                prices=context["prices_data"]["prices"],
                window_size=window_size
            )

            if result.get("success"):
                # Find both min and max for completeness
                min_idx = result["min_window_index"]
                min_sum = result["min_window_sum"]
                max_idx = result["window_sums"].index(max(result["window_sums"]))
                max_sum = result["window_sums"][max_idx]

                return (f"✓ Calculated {result['window_count']} windows of size {window_size} slots. "
                       f"Minimum sum: {min_sum:.2f} at slot {min_idx} ({self._slot_to_time(min_idx)}). "
                       f"Maximum sum: {max_sum:.2f} at slot {max_idx} ({self._slot_to_time(max_idx)}).")
            else:
                return f"✗ Calculation failed: {result.get('error', 'Unknown error')}"

        elif action_type == "CALL_AGENT":
            agent_name = params.get("agent_name")
            user_request = params.get("user_request")

            if not agent_name or not user_request:
                return "✗ Error: Missing agent_name or user_request parameters"

            if "prices_data" not in context:
                return "✗ Error: Must call GET_PRICES before calling agents"

            print(f"\n   [Action] Calling {agent_name}...")
            result = call_appliance_agent(
                agent_name=agent_name,
                prices_data=context["prices_data"],
                user_request=user_request
            )

            # Store agent result ALWAYS (even on error, for debugging)
            appliance_id = agent_name.replace("_agent", "")
            if "agent_results" not in context:
                context["agent_results"] = {}
            context["agent_results"][appliance_id] = result

            if "error" in result:
                return f"✗ Agent error: {result['error']}"

            # Validate agent recommendation against actual price data
            validation_result = self._validate_agent_recommendation(
                result,
                context["prices_data"],
                appliance_id,
                context
            )

            # Format cost (handle None for heat pump)
            cost = result.get('cost')
            cost_str = f"€{cost:.3f}" if cost is not None else "TBD"

            base_msg = f"✓ Agent recommended: Slot {result['recommended_slot']} ({self._slot_to_time(result['recommended_slot'])}), duration {result['duration_slots']} slots, cost {cost_str}. Reasoning: {result['reasoning'][:100]}..."

            # Append validation warning if present
            if validation_result:
                return base_msg + f"\n\n⚠️  VALIDATION WARNING: {validation_result}"

            return base_msg

        elif action_type == "SCHEDULE":
            appliance_id = params.get("appliance_id")
            start_slot = params.get("start_slot")
            duration_slots = params.get("duration_slots")
            reasoning = params.get("reasoning", "LLM orchestrator recommendation")

            # Validate parameters
            try:
                start_slot = int(start_slot)
                duration_slots = int(duration_slots)
            except (ValueError, TypeError):
                return "✗ Error: start_slot and duration_slots must be integers"

            print(f"\n   [Action] Executing schedule for {appliance_id}...")
            schedule_result = schedule_appliance(
                appliance_id=appliance_id,
                start_slot=start_slot,
                duration_slots=duration_slots,
                user_info=reasoning
            )

            if schedule_result.get("success"):
                if "executed_schedules" not in context:
                    context["executed_schedules"] = []
                context["executed_schedules"].append({
                    "appliance_id": appliance_id,
                    "schedule": schedule_result["schedule"]  # Extract just the 96-element array
                })
                return f"✓ Schedule executed: {appliance_id} from {schedule_result['start_time']} to {schedule_result['end_time']} ({schedule_result['duration_minutes']} minutes)"
            else:
                return f"✗ Schedule failed: {schedule_result.get('error', 'Unknown error')}"

        elif action_type == "FINISH":
            summary = params.get("summary", "Orchestration completed.")
            context["final_summary"] = summary
            return f"✓ Orchestration complete. Final summary ready."

        else:
            return f"✗ Unknown action type: {action_type}"

    def _slot_to_time(self, slot: int) -> str:
        """Convert slot index to HH:MM time string."""
        hours = (slot * 15) // 60
        minutes = (slot * 15) % 60
        return f"{hours:02d}:{minutes:02d}"

    def _validate_agent_recommendation(
        self,
        agent_result: Dict[str, Any],
        prices_data: Dict[str, Any],
        appliance_id: str,
        context: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate agent's recommendation against actual price data.
        Returns warning message if significant discrepancy detected, None otherwise.
        """
        # Skip validation for heat pump (complex thermal constraints)
        if appliance_id == "heat_pump":
            return None

        # Extract agent recommendation
        recommended_slot = agent_result.get("recommended_slot")
        duration_slots = agent_result.get("duration_slots")
        agent_cost = agent_result.get("cost")

        if not all([recommended_slot is not None, duration_slots, agent_cost]):
            return None  # Cannot validate without complete data

        # Get appliance power rating
        power_kw = AVAILABLE_APPLIANCES.get(appliance_id, {}).get("power_rating_kw", 1.8)

        # Calculate actual optimal window
        prices = prices_data["prices"]
        min_cost = float('inf')
        optimal_slot = 0

        # Evaluate all possible windows
        for start_slot in range(96 - duration_slots + 1):
            window_prices = prices[start_slot:start_slot + duration_slots]
            # Divide by 1000 to convert EUR/MWh to EUR
            window_cost = sum(price * power_kw * 0.25 / 1000 for price in window_prices)

            if window_cost < min_cost:
                min_cost = window_cost
                optimal_slot = start_slot

        # Calculate agent's window cost for verification
        agent_window_prices = prices[recommended_slot:recommended_slot + duration_slots]
        # Divide by 1000 to convert EUR/MWh to EUR
        agent_window_cost = sum(price * power_kw * 0.25 / 1000 for price in agent_window_prices)

        # Calculate discrepancy
        cost_diff = agent_window_cost - min_cost
        percentage_diff = (cost_diff / min_cost) * 100 if min_cost > 0 else 0

        # Threshold for triggering warning (20% worse than optimal)
        DISCREPANCY_THRESHOLD = 20.0

        if percentage_diff > DISCREPANCY_THRESHOLD:
            # Track retry attempts
            if "agent_retries" not in context:
                context["agent_retries"] = {}
            retry_count = context["agent_retries"].get(appliance_id, 0)

            # Only suggest retry if haven't exceeded max retries
            MAX_RETRIES = 1
            if retry_count < MAX_RETRIES:
                context["agent_retries"][appliance_id] = retry_count + 1
                return (
                    f"Agent recommended slot {recommended_slot} ({self._slot_to_time(recommended_slot)}) "
                    f"at €{agent_window_cost:.4f}, but actual optimal is slot {optimal_slot} "
                    f"({self._slot_to_time(optimal_slot)}) at €{min_cost:.4f}. "
                    f"Discrepancy: {percentage_diff:.1f}% higher than optimal. "
                    f"Consider calling {appliance_id}_agent again with explicit instruction to find the global minimum."
                )
            else:
                return (
                    f"Agent recommended slot {recommended_slot} at €{agent_window_cost:.4f} "
                    f"(actual optimal: slot {optimal_slot} at €{min_cost:.4f}, {percentage_diff:.1f}% discrepancy). "
                    f"Max retries reached - proceeding with agent recommendation."
                )

        return None

    def _save_run_data(self, result: Dict[str, Any], context: Dict[str, Any]) -> None:
        """Save detailed run data to JSON file for dashboard."""
        from datetime import datetime
        import os

        # Calculate total cost from agent results
        agent_results = context.get("agent_results", {})
        total_cost = sum(
            agent_result.get("cost", 0) or 0
            for agent_result in agent_results.values()
        )

        # Prepare run data
        run_data = {
            "timestamp": datetime.now().isoformat(),
            "model": self.model,  # Include model name
            "user_request": result["user_request"],
            "success": result["success"],
            "iterations": result["iterations"],
            "duration_seconds": result.get("duration_seconds", 0),
            "total_tokens": result["total_usage"]["total_tokens"],
            "prompt_tokens": result["total_usage"]["prompt_tokens"],
            "completion_tokens": result["total_usage"]["completion_tokens"],
            "total_cost": total_cost,
            "num_appliances": len(result.get("executed_schedules", [])),
            "appliances_scheduled": [s["appliance_id"] for s in result.get("executed_schedules", [])],
            "prices_data": context.get("prices_data", {}),
            "calendar_constraint": context.get("calendar_constraint", {}),
            "agent_results": context.get("agent_results", {}),
            "executed_schedules": result.get("executed_schedules", []),
            "actions_taken": result.get("actions_taken", []),
            "final_summary": result.get("final_summary", "")
        }

        # Save to model-specific subfolder
        model_folder = f"data/runs/{self.model}"
        os.makedirs(model_folder, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"{model_folder}/run_{timestamp}.json"

        with open(filepath, "w") as f:
            json.dump(run_data, f, indent=2)

        print(f"\n[Saved] Run data: {filepath}")

    def run_scheduling(self, user_request: str) -> Dict[str, Any]:
        """
        Run ReAct-based orchestration workflow.

        Args:
            user_request: User's scheduling request

        Returns:
            Dictionary with scheduling results
        """
        import time
        start_time = time.time()

        print("\n" + "=" * 80)
        print("LLM-BASED ORCHESTRATOR AGENT (ReAct Pattern)")
        print("=" * 80)
        print(f"\nUser Request: {user_request}\n")
        print("=" * 80)

        # Security: Validate and sanitize user input
        print("\n[Security] Validating user input...")
        validation_result = validate_and_prepare_input(user_request)

        if not validation_result["is_valid"]:
            print(f"[Security] ❌ Input rejected - {validation_result['rejection_reason']}")
            if validation_result.get("detected_patterns"):
                print(f"[Security] Detected patterns: {validation_result['detected_patterns']}")
            return {
                "success": False,
                "error": f"Security validation failed: {validation_result['rejection_reason']}",
                "risk_level": validation_result["risk_level"],
                "warnings": validation_result["warnings"],
                "user_request": user_request,
                "actions_taken": [],
                "iterations": 0,
                "total_usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            }

        # Log security warnings (if any)
        if validation_result["warnings"]:
            print(f"[Security] ⚠️  Warnings: {', '.join(validation_result['warnings'])}")
        print(f"[Security] ✓ Input validated (risk level: {validation_result['risk_level']})")

        # Use prepared input (XML-wrapped sanitized content) for privilege separation
        prepared_input = validation_result["prepared_input"]

        # Initialize conversation with privilege-separated input
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prepared_input}
        ]

        context = {}
        total_prompt_tokens = 0
        total_completion_tokens = 0
        actions_taken = []
        max_iterations = 15

        print("\n[LLM Orchestrator] Starting ReAct workflow...\n")

        for iteration in range(max_iterations):
            print(f"\n{'='*80}")
            print(f"Iteration {iteration + 1}")
            print(f"{'='*80}")

            # Get LLM response
            try:
                llm_response, usage = self._call_llm(messages)
                total_prompt_tokens += usage.get('prompt_tokens', 0)
                total_completion_tokens += usage.get('completion_tokens', 0)
            except requests.exceptions.HTTPError as e:
                error_msg = f"API Error: {e.response.status_code} - {e.response.text}"
                print(f"\n[ERROR] {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "actions_taken": actions_taken,
                    "iterations": iteration + 1,
                    "total_usage": {
                        "prompt_tokens": total_prompt_tokens,
                        "completion_tokens": total_completion_tokens,
                        "total_tokens": total_prompt_tokens + total_completion_tokens
                    }
                }
            except Exception as e:
                error_msg = f"Unexpected error calling LLM: {str(e)}"
                print(f"\n[ERROR] {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "actions_taken": actions_taken,
                    "iterations": iteration + 1,
                    "total_usage": {
                        "prompt_tokens": total_prompt_tokens,
                        "completion_tokens": total_completion_tokens,
                        "total_tokens": total_prompt_tokens + total_completion_tokens
                    }
                }

            print(f"\n[LLM Thought/Action]:\n{llm_response}\n")

            # Parse action
            action = self._parse_action(llm_response)

            if not action:
                print("[System] No action detected. Prompting LLM to continue...")
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({"role": "user", "content": "Please output your next ACTION in the required format."})
                continue

            # Execute action
            observation = self._execute_action(action, context)
            actions_taken.append({
                "iteration": iteration + 1,
                "action": action,
                "observation": observation
            })

            print(f"\n[Observation]: {observation}")

            # Add to conversation
            messages.append({"role": "assistant", "content": llm_response})
            messages.append({"role": "user", "content": f"Observation: {observation}\n\nWhat's your next thought and action?"})

            # Check if finished
            if action["type"] == "FINISH":
                duration_seconds = time.time() - start_time

                print("\n" + "=" * 80)
                print("ORCHESTRATOR FINAL SUMMARY")
                print("=" * 80)
                print(context.get("final_summary", "No summary provided."))
                print("=" * 80)
                print(f"\n⏱️  Total execution time: {duration_seconds:.2f} seconds")

                result = {
                    "success": True,
                    "user_request": user_request,
                    "final_summary": context.get("final_summary", ""),
                    "actions_taken": actions_taken,
                    "executed_schedules": context.get("executed_schedules", []),
                    "iterations": iteration + 1,
                    "duration_seconds": duration_seconds,
                    "total_usage": {
                        "prompt_tokens": total_prompt_tokens,
                        "completion_tokens": total_completion_tokens,
                        "total_tokens": total_prompt_tokens + total_completion_tokens
                    }
                }

                # Save detailed run data
                self._save_run_data(result, context)

                return result

        # Max iterations reached
        duration_seconds = time.time() - start_time
        return {
            "success": False,
            "error": "Max iterations reached without FINISH action",
            "actions_taken": actions_taken,
            "duration_seconds": duration_seconds,
            "total_usage": {
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens
            }
        }


def main():
    """Run the ReAct orchestrator with a test query."""
    # Get user query from command line or use default
    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
    else:
        user_query = "Schedule all flexible loads"

    # Initialize ReAct orchestrator
    orchestrator = OrchestratorAgentReAct()

    # Run scheduling workflow
    result = orchestrator.run_scheduling(user_query)

    # Print token usage
    print("\n" + "=" * 80)
    print("TOKEN USAGE (LLM ORCHESTRATOR)")
    print("=" * 80)
    usage = result["total_usage"]
    print(f"  Prompt tokens: {usage['prompt_tokens']}")
    print(f"  Completion tokens: {usage['completion_tokens']}")
    print(f"  Total tokens: {usage['total_tokens']}")
    print(f"  Iterations: {result.get('iterations', 'N/A')}")
    print(f"  Actions taken: {len(result.get('actions_taken', []))}")
    print("=" * 80)

    if result.get("success"):
        print(f"\n✓ Successfully orchestrated {len(result.get('executed_schedules', []))} appliance(s)")


if __name__ == "__main__":
    main()
