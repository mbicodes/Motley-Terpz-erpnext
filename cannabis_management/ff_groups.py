"""Fresh Frozen item groups.

FF items move between these groups automatically by wash yield (doc_hooks/ff_wash_classify.py),
so pages and reports must always use the whole set (or the Fresh Frozen Main subtree), never one group.
"Fresh Frozen" is the single entry dashboards show for all of them, even when it holds no items itself.
"""
FF_ROOT = "Fresh Frozen Main"
FF_UMBRELLA = "Fresh Frozen"
FF_GROUPS = ("Fresh Frozen", "Fresh Frozen - BHO", "Fresh Frozen - SHO", "Fresh Frozen Untested", "Fresh Frozen - To Be Determined")
