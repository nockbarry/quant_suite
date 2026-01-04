"""Visualization modules for analysis workflows."""

from .mcpt_charts import HAS_MATPLOTLIB

# Only export MCPTVisualizer if matplotlib is available
if HAS_MATPLOTLIB:
    from .mcpt_charts import MCPTVisualizer, plot_permutation_distribution
    __all__ = ["MCPTVisualizer", "plot_permutation_distribution", "HAS_MATPLOTLIB"]
else:
    MCPTVisualizer = None
    plot_permutation_distribution = None
    __all__ = ["HAS_MATPLOTLIB"]
