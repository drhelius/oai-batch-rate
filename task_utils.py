import time
import random
from openai_utils import call_openai

def dummy_task(task_id: int):
    """Simulate a task by sleeping for a random duration."""
    time.sleep(random.uniform(0.5, 3.0))

    return {
        'task_id': task_id,
        'tokens': random.randint(5, 100)
    }

def openai_task(task_id: int):
    """Execute a task that calls OpenAI to generate a random number."""
    response = call_openai(f"Task {task_id}: Generate a random number.")

    return {
        'task_id': task_id,
        'tokens': response
    }

