# Pipeline Canary

This page is the fixed input for the OCE pipeline's nightly measurement. Every night the Sweeper asks the CEO to switch the canary line below from `off` to `on`. The request runs through the real small-task Workflow (Triage, Implement, Standards review, Merge and Production), and the change is reverted once it has landed. Because the input is identical every night, a night that takes longer or uses more tokens than the last shows the pipeline growing, not the work.

The change is docs-only and has no deploy. Between runs the line reads `off`.

Canary: off
