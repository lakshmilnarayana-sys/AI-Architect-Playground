from __future__ import annotations

import pandas as pd


def _join_names(
    edges_df: pd.DataFrame,
    nodes_df: pd.DataFrame,
    relationship: str,
    source_is_service: bool,
) -> pd.DataFrame:
    edges = edges_df[edges_df["relationship"] == relationship].copy()
    if edges.empty:
        return pd.DataFrame(columns=["service_id", relationship])

    service_col = "source" if source_is_service else "target"
    related_col = "target" if source_is_service else "source"
    related = nodes_df[["id", "name"]].rename(columns={"id": related_col, "name": relationship})

    return (
        edges[[service_col, related_col]]
        .merge(related, on=related_col, how="left")
        .rename(columns={service_col: "service_id"})
        .groupby("service_id", as_index=False)[relationship]
        .agg(lambda values: ", ".join(sorted(str(v) for v in values if pd.notna(v))))
    )


def build_software_catalog(nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> pd.DataFrame:
    services = nodes_df[nodes_df["label"] == "Service"][["id", "name", "description"]].copy()
    services.rename(columns={"id": "service_id", "name": "Service", "description": "Description"}, inplace=True)

    internal_owners = _join_names(edges_df, nodes_df, "OWNS_SERVICE", source_is_service=False)
    external_owners = _join_names(edges_df, nodes_df, "OWNED_BY_EXTERNAL_TEAM", source_is_service=True)
    oncall = _join_names(edges_df, nodes_df, "HAS_ONCALL_SCHEDULE", source_is_service=True)
    runbooks = _join_names(edges_df, nodes_df, "HAS_RUNBOOK", source_is_service=True)
    dashboards = _join_names(edges_df, nodes_df, "HAS_DASHBOARD", source_is_service=True)
    slos = _join_names(edges_df, nodes_df, "HAS_SLO", source_is_service=True)
    environments = _join_names(edges_df, nodes_df, "DEPLOYED_IN", source_is_service=True)

    dependencies = (
        edges_df[edges_df["relationship"] == "DEPENDS_ON"][["source", "target"]]
        .rename(columns={"source": "service_id"})
        .groupby("service_id", as_index=False)["target"]
        .agg(lambda values: len(set(values)))
        .rename(columns={"target": "Dependency Count"})
    )

    catalog = services
    for frame in [internal_owners, external_owners, oncall, runbooks, dashboards, slos, environments, dependencies]:
        catalog = catalog.merge(frame, on="service_id", how="left")

    catalog["Owner"] = catalog["OWNS_SERVICE"].fillna("")
    has_external = catalog["OWNED_BY_EXTERNAL_TEAM"].fillna("") != ""
    catalog.loc[has_external, "Owner"] = (
        catalog.loc[has_external, "Owner"].where(catalog.loc[has_external, "Owner"] == "", catalog.loc[has_external, "Owner"] + " / ")
        + catalog.loc[has_external, "OWNED_BY_EXTERNAL_TEAM"]
    )

    catalog = catalog.rename(columns={
        "HAS_ONCALL_SCHEDULE": "On-Call Schedule",
        "HAS_RUNBOOK": "Runbook",
        "HAS_DASHBOARD": "Dashboard",
        "HAS_SLO": "SLO",
        "DEPLOYED_IN": "Environment",
    })
    catalog["Dependency Count"] = catalog["Dependency Count"].fillna(0).astype(int)

    return (
        catalog[[
            "Service",
            "Description",
            "Owner",
            "On-Call Schedule",
            "Runbook",
            "Dashboard",
            "SLO",
            "Environment",
            "Dependency Count",
        ]]
        .fillna("Not modeled")
        .replace("", "Not modeled")
        .sort_values("Service")
        .reset_index(drop=True)
    )
