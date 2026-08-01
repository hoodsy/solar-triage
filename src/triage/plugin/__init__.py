"""SolarQuant edge plugin: the trained student served per Ecosuite's plugin
spec (solarquant-zoo/plugin-spec/schema.yaml). One container per SolarNode.

The model is the only decider here. Rules, referee, and batch ingest stay in
the pipeline; the plugin ingests datums, closes local days, computes the same
per-day features the model trained on, and posts prediction datums.
"""
