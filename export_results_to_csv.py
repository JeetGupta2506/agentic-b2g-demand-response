#!/usr/bin/env python3
"""
Export run results to CSV for systematic analysis.
Parses all JSON files in data/runs/ and creates TWO separate CSVs:
1. scheduling_evaluation.csv - for appliance scheduling experiments
2. analytical_query_evaluation.csv - for "avoid 3 hour timeslot" experiments
"""

import json
import csv
import re
from pathlib import Path
from datetime import datetime

# Known optimal slots for reference prices
OPTIMAL_SLOTS = {
    "washing_machine": 10,
    "dishwasher": 11,
    "ev_charger": 1
}

# Correct answer for analytical query (3-hour avoid window)
CORRECT_ANALYTICAL_SLOT = 26  # 06:30-09:30
CORRECT_ANALYTICAL_TIME = "06:30"

def is_analytical_query(user_request):
    """Determine if this is an analytical query (vs scheduling)."""
    query_lower = user_request.lower()
    return any(keyword in query_lower for keyword in ['avoid', 'expensive', 'cheapest', 'timeslot'])

def extract_analytical_answer(data):
    """Extract the model's answer from analytical query run."""
    final_summary = data.get('final_summary', '')

    # Look for time patterns (HH:MM)
    time_matches = re.findall(r'\b(\d{1,2}):(\d{2})\b', final_summary)

    # Look for slot numbers
    slot_matches = re.findall(r'\bslot\s+(\d+)\b', final_summary, re.IGNORECASE)

    if time_matches:
        # Return first time mentioned
        hours, minutes = time_matches[0]
        return f"{hours.zfill(2)}:{minutes}"
    elif slot_matches:
        # Convert slot to time
        slot = int(slot_matches[0])
        hours = (slot * 15) // 60
        minutes = (slot * 15) % 60
        return f"{hours:02d}:{minutes:02d}"

    return final_summary[:100]  # Return truncated summary if no pattern found

def check_analytical_correctness(data):
    """Check if analytical query answer is correct (slot 26 or 06:30)."""
    final_summary = data.get('final_summary', '').lower()

    # Check for slot 26
    if re.search(r'\bslot\s+26\b', final_summary):
        return True

    # Check for 06:30 or 6:30
    if re.search(r'\b0?6:30\b', final_summary):
        return True

    # Check for 07:00 (start of window)
    if re.search(r'\b0?7:00\b', final_summary):
        return True

    return False

def check_tool_usage(data):
    """Check if CALCULATE_WINDOW_SUMS was used."""
    actions = data.get('actions_taken', [])
    for action in actions:
        if action.get('action', {}).get('type') == 'CALCULATE_WINDOW_SUMS':
            return True
    return False

def determine_experimental_stage(data):
    """Determine which experimental stage this run belongs to."""
    timestamp = data.get('timestamp', '')
    tool_used = check_tool_usage(data)

    # Stage detection based on timestamp and tool usage
    # Stage 1 (baseline): Before 2025-10-15 07:40 (no CALCULATE_WINDOW_SUMS available)
    # Stage 2 (minimal guidance): 2025-10-15 07:40 - 07:54 (tool available, minimal guidance)
    # Stage 3 (explicit workflow): After 2025-10-15 07:54 (explicit MAX/MIN guidance)

    try:
        dt = datetime.fromisoformat(timestamp)

        # Stage 3: After explicit workflow added
        if dt >= datetime(2025, 10, 15, 7, 54):
            return "explicit_workflow"
        # Stage 2: Tool available but minimal guidance
        elif dt >= datetime(2025, 10, 15, 7, 40):
            return "minimal_guidance"
        # Stage 1: Baseline (no tool)
        else:
            return "baseline"
    except:
        return "unknown"

def parse_scheduling_run(filepath, data):
    """Parse a scheduling experiment run."""
    prices_date = data.get('prices_data', {}).get('date', '')

    row = {
        'timestamp': data.get('timestamp', ''),
        'model': data.get('model', ''),
        'prices_date': prices_date,
        'user_request': data.get('user_request', ''),
        'iterations': data.get('iterations', 0),
        'duration_seconds': data.get('duration_seconds', 0),
        'orchestrator_actions': len(data.get('actions_taken', [])),
        'total_tokens': data.get('total_tokens', 0),
        'prompt_tokens': data.get('prompt_tokens', 0),
        'completion_tokens': data.get('completion_tokens', 0),
    }

    # Parse agent results and executed schedules
    agent_results = data.get('agent_results', {})
    executed_schedules = data.get('executed_schedules', [])

    # Create set of actually scheduled appliances
    scheduled_appliances = {s['appliance_id'] for s in executed_schedules}

    # Initialize appliance columns
    for appliance in ['washing_machine', 'dishwasher', 'ev_charger']:
        row[f'{appliance}_slot'] = None
        row[f'{appliance}_optimal_slot'] = None
        row[f'{appliance}_is_optimal'] = None
        row[f'{appliance}_cost'] = None
        row[f'{appliance}_tool_calls'] = None

    # Fill in data for scheduled appliances
    for appliance_id in scheduled_appliances:
        if appliance_id in agent_results:
            result = agent_results[appliance_id]
            row[f'{appliance_id}_slot'] = result.get('recommended_slot', None)
            row[f'{appliance_id}_optimal_slot'] = result.get('optimal_slot', None)
            row[f'{appliance_id}_is_optimal'] = result.get('is_optimal', None)
            row[f'{appliance_id}_cost'] = result.get('cost', None)
            row[f'{appliance_id}_tool_calls'] = result.get('tool_call_rounds', None)

    row['success'] = data.get('success', False)

    return row

def parse_analytical_run(filepath, data):
    """Parse an analytical query experiment run."""
    row = {
        'timestamp': data.get('timestamp', ''),
        'model': data.get('model', ''),
        'prices_date': data.get('prices_data', {}).get('date', ''),
        'user_request': data.get('user_request', ''),
        'experimental_stage': determine_experimental_stage(data),
        'iterations': data.get('iterations', 0),
        'duration_seconds': data.get('duration_seconds', 0),
        'orchestrator_actions': len(data.get('actions_taken', [])),
        'total_tokens': data.get('total_tokens', 0),
        'prompt_tokens': data.get('prompt_tokens', 0),
        'completion_tokens': data.get('completion_tokens', 0),
        'tool_used': check_tool_usage(data),
        'correct_answer': check_analytical_correctness(data),
        'model_answer': extract_analytical_answer(data),
        'success': data.get('success', False)
    }

    return row

def export_all_runs_to_csv():
    """Export all run files to TWO separate CSVs based on query type."""
    runs_dir = Path('data/runs')

    if not runs_dir.exists():
        print(f"Error: {runs_dir} does not exist")
        return

    scheduling_rows = []
    analytical_rows = []

    # Traverse all model subdirectories
    for model_dir in runs_dir.iterdir():
        if not model_dir.is_dir():
            continue

        print(f"Processing {model_dir.name}...")

        # Process all JSON files in this model's directory
        for json_file in sorted(model_dir.glob('run_*.json')):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)

                user_request = data.get('user_request', '')

                # Route to appropriate parser based on query type
                if is_analytical_query(user_request):
                    row = parse_analytical_run(json_file, data)
                    analytical_rows.append(row)
                    print(f"  ✓ {json_file.name} [ANALYTICAL]")
                else:
                    row = parse_scheduling_run(json_file, data)
                    scheduling_rows.append(row)
                    print(f"  ✓ {json_file.name} [SCHEDULING]")

            except Exception as e:
                print(f"  ✗ Error parsing {json_file.name}: {e}")

    # Export Scheduling CSV
    if scheduling_rows:
        scheduling_fieldnames = [
            'timestamp',
            'model',
            'prices_date',
            'user_request',
            'iterations',
            'duration_seconds',
            'orchestrator_actions',
            'total_tokens',
            'prompt_tokens',
            'completion_tokens',
            'washing_machine_slot',
            'washing_machine_optimal_slot',
            'washing_machine_is_optimal',
            'washing_machine_cost',
            'washing_machine_tool_calls',
            'dishwasher_slot',
            'dishwasher_optimal_slot',
            'dishwasher_is_optimal',
            'dishwasher_cost',
            'dishwasher_tool_calls',
            'ev_charger_slot',
            'ev_charger_optimal_slot',
            'ev_charger_is_optimal',
            'ev_charger_cost',
            'ev_charger_tool_calls',
            'success'
        ]

        with open('scheduling_evaluation.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=scheduling_fieldnames)
            writer.writeheader()
            writer.writerows(scheduling_rows)

        print(f"\n✓ Exported {len(scheduling_rows)} scheduling runs to scheduling_evaluation.csv")
        print_scheduling_statistics(scheduling_rows)

    # Export Analytical CSV
    if analytical_rows:
        analytical_fieldnames = [
            'timestamp',
            'model',
            'prices_date',
            'user_request',
            'experimental_stage',
            'iterations',
            'duration_seconds',
            'orchestrator_actions',
            'total_tokens',
            'prompt_tokens',
            'completion_tokens',
            'tool_used',
            'correct_answer',
            'model_answer',
            'success'
        ]

        with open('analytical_query_evaluation.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=analytical_fieldnames)
            writer.writeheader()
            writer.writerows(analytical_rows)

        print(f"\n✓ Exported {len(analytical_rows)} analytical query runs to analytical_query_evaluation.csv")
        print_analytical_statistics(analytical_rows)

def print_scheduling_statistics(rows):
    """Print summary statistics for scheduling experiments."""
    print("\nScheduling Experiment Statistics:")
    print("=" * 60)

    models = {}
    for row in rows:
        model = row['model']
        if model not in models:
            models[model] = {
                'total': 0,
                'success': 0,
                'wm_optimal': 0,
                'wm_total': 0,
                'dw_optimal': 0,
                'dw_total': 0,
                'ev_optimal': 0,
                'ev_total': 0,
                'tokens': []
            }

        models[model]['total'] += 1
        if row['success']:
            models[model]['success'] += 1

        # Count optimal per appliance
        if row.get('washing_machine_slot') is not None:
            models[model]['wm_total'] += 1
            if row.get('washing_machine_is_optimal'):
                models[model]['wm_optimal'] += 1

        if row.get('dishwasher_slot') is not None:
            models[model]['dw_total'] += 1
            if row.get('dishwasher_is_optimal'):
                models[model]['dw_optimal'] += 1

        if row.get('ev_charger_slot') is not None:
            models[model]['ev_total'] += 1
            if row.get('ev_charger_is_optimal'):
                models[model]['ev_optimal'] += 1

        if row['total_tokens']:
            models[model]['tokens'].append(row['total_tokens'])

    for model, stats in sorted(models.items()):
        success_rate = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
        avg_tokens = sum(stats['tokens']) / len(stats['tokens']) if stats['tokens'] else 0

        print(f"\n{model}:")
        print(f"  Runs: {stats['total']}")
        print(f"  Success Rate: {success_rate:.1f}%")
        print(f"  Avg Tokens: {avg_tokens:.0f}")

        # Show optimal rates per appliance
        if stats['wm_total'] > 0:
            wm_rate = (stats['wm_optimal'] / stats['wm_total'] * 100)
            print(f"  Washing Machine Optimal: {wm_rate:.1f}% ({stats['wm_optimal']}/{stats['wm_total']})")
        if stats['dw_total'] > 0:
            dw_rate = (stats['dw_optimal'] / stats['dw_total'] * 100)
            print(f"  Dishwasher Optimal: {dw_rate:.1f}% ({stats['dw_optimal']}/{stats['dw_total']})")
        if stats['ev_total'] > 0:
            ev_rate = (stats['ev_optimal'] / stats['ev_total'] * 100)
            print(f"  EV Optimal: {ev_rate:.1f}% ({stats['ev_optimal']}/{stats['ev_total']})")

def print_analytical_statistics(rows):
    """Print summary statistics for analytical query experiments."""
    print("\nAnalytical Query Experiment Statistics:")
    print("=" * 60)

    # Group by model and stage
    models = {}
    for row in rows:
        model = row['model']
        stage = row['experimental_stage']

        if model not in models:
            models[model] = {}

        if stage not in models[model]:
            models[model][stage] = {
                'total': 0,
                'correct': 0,
                'tool_used': 0,
                'tokens': []
            }

        models[model][stage]['total'] += 1
        if row['correct_answer']:
            models[model][stage]['correct'] += 1
        if row['tool_used']:
            models[model][stage]['tool_used'] += 1
        if row['total_tokens']:
            models[model][stage]['tokens'].append(row['total_tokens'])

    for model in sorted(models.keys()):
        print(f"\n{model}:")
        for stage in ['baseline', 'minimal_guidance', 'explicit_workflow']:
            if stage in models[model]:
                stats = models[model][stage]
                correct_rate = (stats['correct'] / stats['total'] * 100) if stats['total'] > 0 else 0
                tool_rate = (stats['tool_used'] / stats['total'] * 100) if stats['total'] > 0 else 0
                avg_tokens = sum(stats['tokens']) / len(stats['tokens']) if stats['tokens'] else 0

                print(f"  {stage}:")
                print(f"    Runs: {stats['total']}")
                print(f"    Correct: {correct_rate:.1f}% ({stats['correct']}/{stats['total']})")
                print(f"    Tool Used: {tool_rate:.1f}% ({stats['tool_used']}/{stats['total']})")
                print(f"    Avg Tokens: {avg_tokens:.0f}")

if __name__ == '__main__':
    export_all_runs_to_csv()
