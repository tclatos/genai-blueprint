# Deer-flow Runtime Context Investigation and Potential Solution

## Investigation Summary

### Question
Could **AioSandboxProvider** solve the ThreadDataMiddleware and file I/O limitations in our Streamlit UI?

### Short Answer
**No.** AioSandboxProvider has the **same dependency** on `runtime.context` that ThreadDataMiddleware has. They are complementary components that work together:
- **ThreadDataMiddleware** creates workspace directories on host
- **AioSandboxProvider** mounts those directories into sandbox containers
- **Both** require `thread_id` from `runtime.context.get("thread_id")`

### Why Can't StreamlitThreadDataMiddleware Enable Bash Tools?

Even if we implement a custom `StreamlitThreadDataMiddleware` that bypasses `runtime.context`:

**It would help:**
- ✅ Python-based file I/O skills (pptx, charts, data analysis)
- ✅ Skills running in Streamlit's process that write files

**It would NOT help:**
- ❌ Bash commands (need a **container** to execute in)
- ❌ Docker tools (need container management)
- ❌ Untrusted code execution (need isolation)

**Why?** Because ThreadDataMiddleware only provides **paths**. Bash tools need an actual **sandbox container** to execute in, which is provided by SandboxProvider. And SandboxProvider also needs `runtime.context`!

See detailed explanation in sections below.

### Answer (Detailed)
**No, but it reveals a potential solution.** AioSandboxProvider and ThreadDataMiddleware are complementary components that both require the same missing piece: `runtime.context`.

## Component Relationships

### ThreadDataMiddleware
**Purpose:** Creates and manages thread-specific workspace directories on the host filesystem.

**What it does:**
```python
def before_agent(self, state, runtime):
    thread_id = runtime.context.get("thread_id")  # ← Requires this!
    
    # Creates directories
    thread_dir = Path(base_dir) / ".deer-flow/threads" / thread_id / "user-data"
    
    paths = {
        "workspace_path": str(thread_dir / "workspace"),
        "uploads_path": str(thread_dir / "uploads"),  
        "outputs_path": str(thread_dir / "outputs"),
    }
    
    # Creates directories (unless lazy_init=True)
    if not self._lazy_init:
        for path in paths.values():
            os.makedirs(path, exist_ok=True)
    
    # Adds to state for skills to use
    return {"thread_data": paths}
```

**Key features:**
- Has `lazy_init=True` mode (only compute paths, don't create dirs)
- Adds `thread_data` dict to agent state
- Skills read `state["thread_data"]["workspace_path"]` to know where to save files

### AioSandboxProvider
**Purpose:** Manages sandbox container lifecycle and mounts workspace into containers.

**What it does:**
```python
def _get_thread_mounts(thread_id: str):
    """Mount thread workspace into sandbox container."""
    thread_dir = Path(base_dir) / ".deer-flow/threads" / thread_id / "user-data"
    
    mounts = [
        # Host path → Container path
        (str(thread_dir / "workspace"), "/virt/workspace", False),
        (str(thread_dir / "uploads"), "/virt/uploads", False),
        (str(thread_dir / "outputs"), "/virt/outputs", False),
    ]
    
    # Creates directories if they don't exist (lazy init)
    for host_path, _, _ in mounts:
        os.makedirs(host_path, exist_ok=True)
        
    return mounts
```

**Key features:**
- Manages Docker/K8s sandbox containers
- Mounts host directories into container at `/virt/{workspace,uploads,outputs}`
- Also creates directories on host (with lazy init)
- Provides isolated execution environment for bash/code tools

### How They Work Together in Deer-flow Native

```
User Request 
    ↓
LangGraph Runtime (provides runtime.context with thread_id)
    ↓
ThreadDataMiddleware.before_agent()
    ├─ Reads thread_id from runtime.context
    ├─ Creates workspace directories on host
    └─ Adds thread_data to state
    ↓
Agent Execution
    ↓
Skill/Tool needs file I/O
    ├─ Reads state["thread_data"]["workspace_path"]
    ├─ Writes file to /path/to/workspace/output.pptx
    └─ OR (if in sandbox): writes to /virt/workspace/output.pptx
    ↓
AioSandboxProvider (if sandbox enabled)
    ├─ Reads thread_id (same source: runtime.context)
    ├─ Mounts host workspace → /virt/workspace in container
    └─ Tool executes in isolated container with mounted workspace
```

## Why Our Current Approach Fails

When using `create_deer_flow_agent_simple()`, we call:

```python
agent = create_agent(
    agent=agent_callable,
    checkpointer=checkpointer,
    middlewares=middlewares,
    state_schema=ThreadState,
)
```

This creates a standalone LangGraph `CompiledStateGraph` **without** deer-flow's runtime infrastructure. When LangGraph executes:

```python
async for step in agent.astream(inputs, config):
    # LangGraph provides runtime to middlewares
    # But runtime.context is None!
```

The `runtime` object exists but `runtime.context` is `None`, causing:
```python
thread_id = runtime.context.get("thread_id")
# AttributeError: 'NoneType' object has no attribute 'get'
```

## Potential Solution: Runtime Context Mocking

### Approach 1: Mock ThreadDataMiddleware (Non-Sandbox)

For **file-based skills without sandbox**, we could mock runtime.context:

```python
# In create_deer_flow_agent_simple()

# Import required middleware
from src.agents.middlewares.thread_data_middleware import ThreadDataMiddleware

# Build middlewares but keep ThreadDataMiddleware
middlewares = _build_middlewares(middleware_config)

# Don't remove ThreadDataMiddleware for Streamlit!
middlewares_to_remove = [
    UploadsMiddleware,      # Still needs file upload UI
    TitleMiddleware,        # Still needs thread history
    MemoryMiddleware,       # Still needs persistent store
]
if not interactive_mode:
    middlewares_to_remove.append(ClarificationMiddleware)

middlewares = [m for m in middlewares if not any(isinstance(m, cls) for cls in middlewares_to_remove)]

# Create ThreadDataMiddleware with lazy_init=True
# (don't create dirs until skill actually needs them)
thread_data_mw = ThreadDataMiddleware(
    base_dir=str(Path.cwd()),  # Or configurable workspace dir
    lazy_init=True
)
middlewares.insert(0, thread_data_mw)

# Then create agent as normal...
```

**But this still fails** because middleware's `before_agent()` is called by LangGraph with `runtime.context=None`.

### Approach 2: Custom Middleware Wrapper

Create a wrapper that injects thread_id from our config:

```python
class StreamlitThreadDataMiddleware(AgentMiddleware):
    """Wrapper that provides thread_id without runtime.context."""
    
    def __init__(self, base_dir: str | None = None):
        super().__init__()
        self._base_dir = base_dir or os.getcwd()
        
    def before_agent(self, state, runtime):
        # Get thread_id from config instead of runtime.context
        # LangGraph passes config via runtime
        thread_id = runtime.config.get("configurable", {}).get("thread_id")
        
        if not thread_id:
            # Fallback: generate from state or use default
            thread_id = "streamlit-session"
            
        # Compute paths (same as ThreadDataMiddleware)
        thread_dir = Path(self._base_dir) / ".deer-flow/threads" / thread_id / "user-data"
        
        paths = {
            "workspace_path": str(thread_dir / "workspace"),
            "uploads_path": str(thread_dir / "uploads"),
            "outputs_path": str(thread_dir / "outputs"),
        }
        
        # Create directories
        for path in paths.values():
            os.makedirs(path, exist_ok=True)
            
        # Add to state
        return {"thread_data": paths}
```

**Usage in Streamlit:**
```python
# In deer_flow_agent.py create_agent_for_profile()

# Add custom middleware instead of ThreadDataMiddleware
from genai_blueprint.webapp.middlewares.streamlit_thread_data import StreamlitThreadDataMiddleware

workspace_dir = Path.cwd() / ".deer-flow-streamlit"  # Custom workspace
thread_data_mw = StreamlitThreadDataMiddleware(base_dir=str(workspace_dir))

middlewares = [thread_data_mw] + other_middlewares
```

### Approach 3: Modify deer-flow Integration

Patch the agent creation to inject context:

```python
def create_deer_flow_agent_with_context(
    profile: DeerFlowAgentConfig,
    llm: Any,
    thread_id: str,
    workspace_dir: Path | None = None,
    **kwargs
):
    """Create agent with mocked runtime context support."""
    
    # Use custom middleware that gets thread_id from config
    from genai_blueprint.webapp.middlewares.streamlit_thread_data import StreamlitThreadDataMiddleware
    
    workspace_dir = workspace_dir or Path.cwd() / ".deer-flow-streamlit"
    
    # Build middlewares
    middlewares = _build_middlewares(config)
    
    # Replace ThreadDataMiddleware with our custom one
    middlewares = [m for m in middlewares if not isinstance(m, ThreadDataMiddleware)]
    thread_data_mw = StreamlitThreadDataMiddleware(base_dir=str(workspace_dir))
    middlewares.insert(0, thread_data_mw)
    
    # Remove other context-dependent middlewares as before
    # ... rest of agent creation
```

## Recommended Path Forward

### Short Term (Current State)
✅ **Keep current implementation** - Document limitations clearly
- No ThreadDataMiddleware in CLI/Streamlit
- Skills requiring file I/O won't work
- Recommend deer-flow native UI for those use cases

### Medium Term (Experimental)
🔬 **Implement StreamlitThreadDataMiddleware** (Approach 2/3)
- Custom middleware that doesn't need runtime.context
- Gets thread_id from LangGraph config
- Creates workspace in Streamlit-specific location
- **Limitations:**
  - Only works for file-based skills (no sandbox)
  - Files saved to Streamlit workspace, not container
  - Bash/docker tools still won't work
  - Skills expecting `/virt/workspace` paths will break

**Why bash/sandbox tools still won't work:**

ThreadDataMiddleware and SandboxProvider serve **different purposes**:

1. **ThreadDataMiddleware** → Creates workspace directories on the **HOST** filesystem
   - Adds paths to state: `state["thread_data"]["workspace_path"]`
   - Skills **running in Streamlit's Python process** can use these paths
   - Example: `pptx_lib.save(state["thread_data"]["workspace_path"] + "/output.pptx")`
   - Works because the skill code runs in the **same process** as Streamlit

2. **SandboxProvider** → Creates and manages **CONTAINERS** for isolated execution
   - Provisions Docker/K8s containers
   - Mounts workspace into container at `/virt/workspace`
   - Provides isolated environment to run **untrusted code**
   - Example: `sandbox.run_code("bash", "rm -rf /")`  # Isolated, won't harm host

**The execution flow for bash tools:**
```python
# When agent tries to execute bash command:
1. Tool calls: sandbox.run_code("bash", "echo hello > /virt/workspace/file.txt")

2. SandboxProvider needs to:
   - Get or create a container for this thread  # ← Needs thread_id!
   - Mount host workspace → /virt/workspace in container
   - Execute the bash command INSIDE the container
   - Return results from container

3. Without SandboxProvider:
   - ❌ No container exists to run bash in
   - ❌ Can't execute untrusted code safely
   - ❌ No "/virt/workspace" path (only exists inside container)
   - ❌ Would have to run bash directly on host (security risk!)
```

**The problem:** SandboxProvider **ALSO** requires `runtime.context`:

```python
# From aio_sandbox_provider.py
def acquire(self, thread_id: str | None = None) -> str:
    """Get or create a sandbox for a thread."""
    if thread_id:
        # Needs thread_id to mount correct workspace!
        extra_mounts = self._get_extra_mounts(thread_id)  # ← Needs thread_id!
        # Mounts: /host/threads/{thread_id}/workspace → /virt/workspace
```

**What would work vs. not work:**

✅ **Would work with StreamlitThreadDataMiddleware:**
- `ppt-generation` - Python library (python-pptx) running in Streamlit process
- `chart-visualization` - Python plotting (matplotlib/plotly) in Streamlit process  
- `data-analysis` - Pandas operations in Streamlit process
- Any skill using Python APIs to write files

❌ **Would NOT work (need SandboxProvider):**
- `run_bash_command` - No container to execute bash safely
- Docker-based tools - No container runtime
- Skills calling `sandbox.run_code()` - No sandbox exists
- Video generation via CLI tools - Would need container for ffmpeg/etc
- Image generation via external binaries - Would need container isolation

**To enable bash/docker tools would require:**
1. StreamlitThreadDataMiddleware (workspace paths) ✅ Feasible
2. StreamlitSandboxProvider (container management) ❌ Very complex:
   - Must provision Docker containers from Streamlit
   - Must manage container lifecycle, ports, cleanup
   - Must handle thread_id → container mapping
   - Security concerns: running untrusted code from web UI
   - Requires Docker daemon access from Streamlit process

This is why we recommend deer-flow's native UI for full sandbox support.

### Long Term (Architecture Change)
🏗️ **Request deer-flow enhancement** to support external runtime context
- Proposal: Allow runtime.context injection at graph creation
- Benefit: Enables proper integration in Streamlit, Jupyter, etc.
- Example API:
  ```python
  agent = create_agent(
      agent=agent_callable,
      checkpointer=checkpointer,
      middlewares=middlewares,
      state_schema=ThreadState,
      runtime_context={"thread_id": thread_id}  # ← New parameter
  )
  ```

## Implementation Checklist

If choosing to implement StreamlitThreadDataMiddleware:

- [ ] Create `genai_blueprint/webapp/middlewares/streamlit_thread_data.py`
- [ ] Implement `StreamlitThreadDataMiddleware` class
- [ ] Add workspace directory configuration
- [ ] Update `create_agent_for_profile()` to use custom middleware
- [ ] Add workspace cleanup utilities
- [ ] Document which skills will/won't work
- [ ] Test with ppt-generation, image-generation skills
- [ ] Add file browser UI to view generated files
- [ ] Add download buttons for workspace files

## Testing Strategy

```python
# Test file I/O without sandbox
>>> generate a PowerPoint with Einstein quotes

Expected:
- Middleware creates: .deer-flow-streamlit/threads/{thread_id}/user-data/workspace/
- Skill gets: state["thread_data"]["workspace_path"]
- Skill writes: {workspace_path}/einstein_quotes.pptx
- UI shows: Download button for generated file

# Test skills requiring sandbox (will still fail)
>>> run bash command: ls -la

Expected:
- No sandbox available
- Error: "Sandbox not available in Streamlit mode"
```

## Conclusion

**AioSandboxProvider does NOT solve our problem** because:
1. It requires the same `runtime.context.get("thread_id")` that ThreadDataMiddleware needs
2. It's for sandbox container management, not a replacement for workspace management
3. They work together, not as alternatives

**A potential solution exists** via custom middleware that:
- Bypasses runtime.context requirement
- Gets thread_id from LangGraph config
- Works for file-based skills only (no sandbox)
- Requires careful documentation of limitations

This is an **experimental approach** with significant limitations. For production use cases requiring full skill support, deer-flow's native web interface remains the recommended solution.
