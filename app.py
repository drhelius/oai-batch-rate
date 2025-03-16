import streamlit as st
from batch_processor import BatchProcessor
from task_utils import openai_task
from streamlit_autorefresh import st_autorefresh
from timer import Timer
import pandas as pd
import time
import altair as alt

# Default configuration values
DEFAULT_NUM_EXECUTORS = 3
DEFAULT_NUM_TASKS = 10
DEFAULT_RESULTS_TO_SHOW = 10
MAX_EXECUTORS = 50
MAX_TASKS = 1000
MAX_HISTORY = 60
REFRESH_INTERVAL = 500
DEFAULT_MAX_RPM = 100
DEFAULT_MAX_TPM = 10000

# Set page config
st.set_page_config(
    page_title="Batch Processing Demo",
    layout="wide",
    initial_sidebar_state="expanded"
)

def initialize_session_state():
    if 'processor' not in st.session_state:
        st.session_state.processor = BatchProcessor(num_executors=DEFAULT_NUM_EXECUTORS)
    
    if 'timer' not in st.session_state:
        st.session_state.timer = Timer()
    
    # Metrics tracking
    for key in ['prev_completed_tasks', 'prev_queue_size', 'prev_tokens', 
                'prev_tpm', 'prev_rpm', 'prev_qps']:
        if key not in st.session_state:
            st.session_state[key] = 0
    
    # History tracking
    for key in ['tpm_history', 'rpm_history', 'token_history', 'metric_times']:
        if key not in st.session_state:
            st.session_state[key] = []
            
    # Rate limiting settings
    if 'rate_limit_mode' not in st.session_state:
        st.session_state.rate_limit_mode = "unlimited"
    if 'max_rpm' not in st.session_state:
        st.session_state.max_rpm = DEFAULT_MAX_RPM
    if 'max_tpm' not in st.session_state:
        st.session_state.max_tpm = DEFAULT_MAX_TPM

# Callback function for when rate limit mode changes
def on_rate_limit_mode_change():
    # This is called whenever the radio button value changes
    pass

def render_sidebar():
    with st.sidebar:
        st.header("Configuration")
        
        num_executors = st.slider("Number of Executors", 1, MAX_EXECUTORS, DEFAULT_NUM_EXECUTORS, key="num_executors_slider")
        num_tasks = st.number_input("Number of Tasks", 1, MAX_TASKS, DEFAULT_NUM_TASKS, key="num_tasks_input")
        
        st.markdown("---")
        st.subheader("Rate Limiting")
        
        # Get the current mode from session state without modifying it after widget creation
        current_mode = st.session_state.rate_limit_mode
        
        # Create the radio button with the current value from session state
        rate_limit_mode = st.radio(
            "Rate Limit Mode",
            ["unlimited", "limited"],
            index=0 if current_mode == "unlimited" else 1,
            key="rate_limit_mode",
            on_change=on_rate_limit_mode_change
        )
        
        # Show rate limit settings if limited mode is selected
        if rate_limit_mode == "limited":
            max_rpm = st.number_input(
                "Max Requests per Minute (RPM)", 
                min_value=0, 
                max_value=10000, 
                value=st.session_state.max_rpm,
                key="max_rpm_input",
                help="Set to 0 for unlimited RPM"
            )
            
            max_tpm = st.number_input(
                "Max Tokens per Minute (TPM)", 
                min_value=0, 
                max_value=1000000, 
                value=st.session_state.max_tpm,
                key="max_tpm_input",
                help="Set to 0 for unlimited TPM"
            )
            
            st.session_state.max_rpm = max_rpm
            st.session_state.max_tpm = max_tpm
        else:
            max_rpm = 0
            max_tpm = 0
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("▶️ Start", key="start_button", use_container_width=True):
                start_processing(num_executors, num_tasks, rate_limit_mode, max_rpm, max_tpm)
        
        with col2:
            if st.button("⏹️ Stop", key="stop_button", use_container_width=True):
                st.session_state.processor.stop()
                st.session_state.timer.stop()
        
        st.markdown("---")
        st.subheader("Display Settings")
        num_results_to_show = st.slider("Results to Show", 3, 20, DEFAULT_RESULTS_TO_SHOW, key="results_count_slider")
        
        return num_executors, num_tasks, num_results_to_show, rate_limit_mode, max_rpm, max_tpm

def start_processing(num_executors, num_tasks, rate_limit_mode, max_rpm, max_tpm):
    processor = st.session_state.processor
    timer = st.session_state.timer
    
    processor.reset(num_executors=num_executors)
    processor.set_rate_limits(mode=rate_limit_mode, max_rpm=max_rpm, max_tpm=max_tpm)
    
    for i in range(num_tasks):
        processor.add_task(openai_task, i)
    processor.start()
    timer.start()
    
    # Reset metrics and history
    st.session_state.tpm_history = []
    st.session_state.rpm_history = []
    st.session_state.token_history = []
    st.session_state.metric_times = []
    st.session_state.prev_completed_tasks = 0
    st.session_state.prev_queue_size = 0
    st.session_state.prev_tokens = 0
    st.session_state.prev_tpm = 0
    st.session_state.prev_rpm = 0
    st.session_state.prev_qps = 0

def update_metrics():
    processor = st.session_state.processor
    progress = processor.get_progress()
    current_time = time.monotonic()
    
    # Calculate deltas
    completed_delta = progress['completed'] - st.session_state.prev_completed_tasks
    st.session_state.prev_completed_tasks = progress['completed']
    
    queue_size_delta = progress['queue_size'] - st.session_state.prev_queue_size
    st.session_state.prev_queue_size = progress['queue_size']
    
    tpm = progress.get('tpm', 0)
    tpm_delta = tpm - st.session_state.prev_tpm
    st.session_state.prev_tpm = tpm
    
    rpm = progress.get('rpm', 0)
    rpm_delta = rpm - st.session_state.prev_rpm
    st.session_state.prev_rpm = rpm
    
    qps = progress.get('qps', 0)
    st.session_state.prev_qps = qps
    
    tokens = progress.get('total_tokens', 0)
    tokens_delta = max(tokens - st.session_state.prev_tokens, 0)
    st.session_state.prev_tokens = tokens
    
    # Store metrics history
    st.session_state.tpm_history.append(tpm)
    st.session_state.rpm_history.append(rpm)
    st.session_state.token_history.append(tokens_delta)
    st.session_state.metric_times.append(current_time)
    
    # Keep only the latest data points
    if len(st.session_state.tpm_history) > MAX_HISTORY:
        st.session_state.tpm_history = st.session_state.tpm_history[-MAX_HISTORY:]
        st.session_state.rpm_history = st.session_state.rpm_history[-MAX_HISTORY:]
        st.session_state.token_history = st.session_state.token_history[-MAX_HISTORY:]
        st.session_state.metric_times = st.session_state.metric_times[-MAX_HISTORY:]
    
    return {
        'progress': progress,
        'current_time': current_time,
        'completed_delta': completed_delta,
        'queue_size_delta': queue_size_delta,
        'tpm': tpm,
        'tpm_delta': tpm_delta,
        'rpm': rpm,
        'rpm_delta': rpm_delta, 
        'qps': qps,
        'tokens': tokens,
        'tokens_delta': tokens_delta
    }

def render_overview_metrics(metrics):
    progress = metrics['progress']
    timer = st.session_state.timer
    
    st.subheader("Overview")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        elapsed_time = timer.elapsed()
        label = "Total Time" if progress['completed'] == progress['total'] else "Elapsed Time"
        st.metric(label=label, value=f"{elapsed_time:.2f}s")
    
    with col2:
        completed_delta = metrics['completed_delta']
        st.metric(
            label="Tasks Completed",
            value=f"{progress['completed']}/{progress['total']}",
            delta=completed_delta if completed_delta != 0 else None
        )
    
    with col3:
        st.metric(label="Executors", value=st.session_state.processor.num_executors)
    
    with col4:
        queue_size_delta = metrics['queue_size_delta']
        st.metric(
            label="Queue Size",
            value=progress['queue_size'],
            delta=queue_size_delta if queue_size_delta != 0 else None,
            delta_color="inverse"
        )
    
    with col5:
        st.metric(
            label="Errors",
            value=progress.get('error_count', 0),
            delta=progress.get('error_count', 0) if progress.get('error_count', 0) > 0 else None,
            delta_color="inverse"
        )

def render_performance_metrics(metrics):
    progress = metrics['progress']
    
    st.subheader("Performance")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="TPM",
            value=metrics['tpm'],
            delta=metrics['tpm_delta'] if metrics['tpm_delta'] != 0 else None
        )
    
    with col2:
        st.metric(
            label="RPM",
            value=metrics['rpm'],
            delta=metrics['rpm_delta'] if metrics['rpm_delta'] != 0 else None
        )
    
    with col3:
        st.metric(
            label="QPS",
            value=metrics['qps']
        )
    
    with col4:
        st.metric(
            label="Requeued Tasks",
            value=progress.get('requeued_tasks', 0)
        )

    st.markdown("---")
    
    # Display rate limiter info if in limited mode
    if progress.get('rate_limit_mode') == "limited" and progress.get('rate_limit_info'):
        rate_info = progress.get('rate_limit_info')
        if rate_info:
            st.subheader("Rate Limiter Status")
            
            # First row - RPM and TPM info
            rate_cols = st.columns(4)
            with rate_cols[0]:
                max_rpm = rate_info.get('max_rpm', 0)
                current_rpm = rate_info.get('rpm', 0)
                rpm_text = f"{current_rpm}/{max_rpm}" if max_rpm > 0 else "Unlimited"
                st.metric(label="Current/Max RPM", value=rpm_text)
            
            with rate_cols[1]:
                max_tpm = rate_info.get('max_tpm', 0)
                current_tpm = rate_info.get('tpm', 0)
                tpm_text = f"{current_tpm}/{max_tpm}" if max_tpm > 0 else "Unlimited"
                st.metric(label="Current/Max TPM", value=tpm_text)
            
            with rate_cols[2]:
                rpm_usage = 0
                if max_rpm > 0 and current_rpm > 0:
                    rpm_usage = int((current_rpm / max_rpm) * 100)
                st.metric(label="RPM Usage %", value=f"{rpm_usage}%")
            
            with rate_cols[3]:
                tpm_usage = 0
                if max_tpm > 0 and current_tpm > 0:
                    tpm_usage = int((current_tpm / max_tpm) * 100)
                st.metric(label="TPM Usage %", value=f"{tpm_usage}%")
            
            # Second row - Window-specific info for RPM
            st.markdown("#### RPM Window Details")
            rpm_window_size = rate_info.get('rpm_window_size', 10)
            st.write(f"RPM Window Size: {rpm_window_size} seconds")
            
            window_cols = st.columns(4)
            with window_cols[0]:
                rpm_window_requests = rate_info.get('rpm_window_requests', 0)
                rpm_window_max_requests = rate_info.get('rpm_window_max_requests', 0) 
                if rpm_window_max_requests > 0:
                    st.metric(
                        label=f"Requests in {rpm_window_size}s window", 
                        value=f"{rpm_window_requests}/{rpm_window_max_requests:.1f}"
                    )
                else:
                    st.metric(label=f"Requests in {rpm_window_size}s window", value="Unlimited")
            
            with window_cols[1]:
                window_rpm = rate_info.get('window_rpm', 0)
                st.metric(label="Window-based RPM", value=f"{window_rpm}")
            
            # Calculate and show window usage percentages
            with window_cols[2]:
                rpm_window_usage = 0
                if rpm_window_max_requests > 0 and rpm_window_requests > 0:
                    rpm_window_usage = int((rpm_window_requests / rpm_window_max_requests) * 100)
                st.metric(label="Window Request Usage", value=f"{rpm_window_usage}%")
            
            # Third row - Window-specific info for TPM
            st.markdown("#### TPM Window Details")
            tpm_window_size = rate_info.get('tpm_window_size', 60)
            st.write(f"TPM Window Size: {tpm_window_size} seconds")
            
            tpm_window_cols = st.columns(4)
            with tpm_window_cols[0]:
                tpm_window_tokens = rate_info.get('tpm_window_tokens', 0)
                tpm_window_max_tokens = rate_info.get('tpm_window_max_tokens', 0)
                if tpm_window_max_tokens > 0:
                    st.metric(
                        label=f"Tokens in {tpm_window_size}s window", 
                        value=f"{tpm_window_tokens:.0f}/{tpm_window_max_tokens:.0f}"
                    )
                else:
                    st.metric(label=f"Tokens in {tpm_window_size}s window", value="Unlimited") 
            
            with tpm_window_cols[1]:
                window_tpm = rate_info.get('window_tpm', 0)
                st.metric(label="Window-based TPM", value=f"{window_tpm}")
                
            with tpm_window_cols[2]:
                tpm_window_usage = 0
                if tpm_window_max_tokens > 0 and tpm_window_tokens > 0:
                    tpm_window_usage = int((tpm_window_tokens / tpm_window_max_tokens) * 100)
                st.metric(label=f"Window Token Usage", value=f"{tpm_window_usage}%")

def render_token_statistics(metrics):
    progress = metrics['progress']
    
    st.subheader("Token Statistics")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Min Tokens",
            value=progress.get('min_tokens', 0)
        )
    
    with col2:
        st.metric(
            label="Max Tokens",
            value=progress.get('max_tokens', 0)
        )
    
    with col3:
        st.metric(
            label="Avg Tokens",
            value=progress.get('avg_tokens', 0)
        )
    
    with col4:
        st.metric(
            label="Total Tokens",
            value=progress.get('total_tokens', 0),
            delta=metrics['tokens_delta'] if metrics['tokens_delta'] != 0 else None
        )

def render_charts(metrics):
    current_time = metrics['current_time']
    
    # Create relative timestamps
    relative_times = [(t - current_time) for t in st.session_state.metric_times]
    
    # Create dataframes for all three charts
    tpm_data = pd.DataFrame({
        'Time': relative_times if relative_times else [0],
        'TPM': st.session_state.tpm_history if st.session_state.tpm_history else [0]
    })
    
    rpm_data = pd.DataFrame({
        'Time': relative_times if relative_times else [0],
        'RPM': st.session_state.rpm_history if st.session_state.rpm_history else [0]
    })
    
    tokens_data = pd.DataFrame({
        'Time': relative_times if relative_times else [0],
        'Tokens': st.session_state.token_history if st.session_state.token_history else [0]
    })
    
    # Determine the domain for x-axis
    x_min = min(relative_times) if relative_times else -60  # Default to -60 seconds for empty charts
    x_max = max(relative_times) if relative_times else 0    # Default to 0 for empty charts
    
    chart_height = 140
    
    # TPM Chart
    st.subheader("Tokens Per Minute")
    tpm_chart = alt.Chart(tpm_data).mark_line(point=False).encode(
        x=alt.X('Time', scale=alt.Scale(domain=[x_min, x_max])),
        y=alt.Y('TPM', axis=alt.Axis(title=None))
    ).properties(height=chart_height)
    st.altair_chart(tpm_chart, use_container_width=True)
    
    # RPM Chart
    st.subheader("Requests Per Minute")
    rpm_chart = alt.Chart(rpm_data).mark_line(point=False).encode(
        x=alt.X('Time', scale=alt.Scale(domain=[x_min, x_max])),
        y=alt.Y('RPM', axis=alt.Axis(title=None))
    ).properties(height=chart_height)
    st.altair_chart(rpm_chart, use_container_width=True)
    
    # Tokens per refresh chart
    st.subheader("Tokens Per Refresh")
    tokens_chart = alt.Chart(tokens_data).mark_bar().encode(
        x=alt.X('Time', scale=alt.Scale(domain=[x_min, x_max])),
        y=alt.Y('Tokens', axis=alt.Axis(title=None))
    ).properties(height=chart_height)
    st.altair_chart(tokens_chart, use_container_width=True)

def render_results(results, num_results_to_show):
    st.subheader("Latest Results")
    
    # Custom CSS for reducing vertical spacing in results
    st.markdown("""
    <style>
    div.row-widget.stHorizontal {
        margin-top: -0.5rem;
        margin-bottom: -0.5rem;
    }
    hr {
        margin-top: 0.3rem !important;
        margin-bottom: 0.3rem !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    if results:
        # Table header row using columns
        result_cols = st.columns([1, 2, 1])
        with result_cols[0]:
            st.write("**Executor**")
        with result_cols[1]:
            st.write("**Task Details**")
        with result_cols[2]:
            st.write("**Metrics**")
        
        # Show the number selected in the sidebar, newest first
        last_results = results[-num_results_to_show:]
        
        for result in reversed(last_results):
            cols = st.columns([1, 2, 1])
            
            with cols[0]:
                st.write(f"Executor {result['executor_id']}")
            
            with cols[1]:
                status = result.get('status', 'success')
                if status == 'error':
                    task_id = result.get('task_result', {}).get('task_id', "Unknown")
                    error_text = result.get('error', 'Unknown error')
                    st.write(f"Task {task_id} - ❌ Error: {error_text}")
                else:
                    task_id = result['task_result']['task_id']
                    st.write(f"✅ Task {task_id} completed")
            
            with cols[2]:
                st.write(
                    f"⏱️ {result['execution_time']:.2f}s | "
                    f"🔤 {result['task_result'].get('tokens', 0)}"
                )
            
    else:
        st.info("No results to display yet.")

def render_main_dashboard(num_executors, num_results_to_show):
    metrics = update_metrics()
    progress = metrics['progress']
    
    if progress['total'] > 0:
        # Progress indicator
        progress_pct = min(100, int(100 * progress['completed'] / progress['total']))
        
        # Status message
        if progress['completed'] == progress['total'] and progress['total'] > 0:
            if st.session_state.timer.running:
                st.session_state.timer.stop()
            st.success("✅ All tasks completed!")
        elif st.session_state.processor.remaining_tasks() > 0:
            st.info("⏳ Processing tasks...")
        
        # Progress bar
        st.progress(progress_pct / 100)
        
        # Layout: metrics on left, charts on right
        left_col, right_col = st.columns([3, 2])
        
        with left_col:
            render_overview_metrics(metrics)
            st.markdown("---")
            render_token_statistics(metrics)
            st.markdown("---")
            render_performance_metrics(metrics)
            
        
        with right_col:
            render_charts(metrics)
        
        st.markdown("---")

        # Results section (full width)
        render_results(progress['results'], num_results_to_show)
    else:
        st.info("Configure your batch processing parameters in the sidebar and click 'Start' to begin.")

def main():
    initialize_session_state()
    num_executors, num_tasks, num_results_to_show, rate_limit_mode, max_rpm, max_tpm = render_sidebar()
    
    st.title("Batch Processing Dashboard")
    render_main_dashboard(num_executors, num_results_to_show)
    
    st_autorefresh(interval=REFRESH_INTERVAL, key="auto_refresh")

if __name__ == "__main__":
    main()
