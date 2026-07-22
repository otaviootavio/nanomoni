#!/usr/bin/env python3
"""Common PromQL metric queries shared across all payment modes."""

from typing import Any, Dict, List

# Common resource charts (issuer, client, vendor) that apply to all payment modes
COMMON_CHARTS: List[Dict[str, Any]] = [
    {
        "title": "Issuer Network (KiB/s)",
        "section": "issuer_resources",
        "queries": [
            {
                "promql": 'sum(\n  rate(container_network_receive_bytes_total{\n    job="cadvisor",\n    container_label_com_docker_compose_service="issuer",\n    image!=""\n  }[30s])\n) / 1024',
                "legend": "Input",
            },
            {
                "promql": 'sum(\n  rate(container_network_transmit_bytes_total{\n    job="cadvisor",\n    container_label_com_docker_compose_service="issuer",\n    image!=""\n  }[30s])\n) / 1024',
                "legend": "Output",
            },
        ],
    },
    {
        "title": "Issuer Memory Usage (MiB)",
        "section": "issuer_resources",
        "queries": [
            {
                "promql": 'sum(\n  container_memory_usage_bytes{\n    job="cadvisor",\n    container_label_com_docker_compose_service="issuer",\n    image!=""\n  }\n) / 1024 / 1024',
                "legend": "__auto",
            }
        ],
    },
    {
        "title": "Issuer CPU Usage (Cores)",
        "section": "issuer_resources",
        "queries": [
            {
                "promql": 'sum(\n  rate(container_cpu_usage_seconds_total{\n    job="cadvisor",\n    container_label_com_docker_compose_service="issuer",\n    image!=""\n  }[30s])\n)',
                "legend": "__auto",
            }
        ],
    },
    {
        "title": "Issuer Redis Memory Usage (MiB)",
        "section": "issuer_resources",
        "queries": [
            {
                "promql": 'container_memory_working_set_bytes{container_label_com_docker_compose_service="redis-issuer", image!=""} / 1024 / 1024',
                "legend": "Redis Issuer Memory",
            }
        ],
    },
    {
        "title": "Issuer Redis CPU Usage (Cores)",
        "section": "issuer_resources",
        "queries": [
            {
                "promql": 'rate(container_cpu_usage_seconds_total{job="cadvisor", name="nanomoni-redis-issuer-1", image!=""}[30s])',
                "legend": "Redis Issuer CPU",
            }
        ],
    },
    {
        "title": "Client Network (KiB/s)",
        "section": "client_resources",
        "queries": [
            {
                "promql": 'sum(\n  rate(container_network_receive_bytes_total{\n    job="cadvisor",\n    container_label_com_docker_compose_service="client",\n    image!=""\n  }[30s])\n) / 1024',
                "legend": "Input",
            },
            {
                "promql": 'sum(\n  rate(container_network_transmit_bytes_total{\n    job="cadvisor",\n    container_label_com_docker_compose_service="client",\n    image!=""\n  }[30s])\n) / 1024',
                "legend": "Output",
            },
        ],
    },
    {
        "title": "Client Memory Usage (MiB)",
        "section": "client_resources",
        "queries": [
            {
                "promql": 'sum(\n  container_memory_usage_bytes{\n    job="cadvisor",\n    container_label_com_docker_compose_service="client",\n    image!=""\n  }\n) / 1024 / 1024',
                "legend": "__auto",
            }
        ],
    },
    {
        "title": "Client CPU Usage (Cores)",
        "section": "client_resources",
        "queries": [
            {
                "promql": 'sum(\n  rate(container_cpu_usage_seconds_total{\n    job="cadvisor",\n    container_label_com_docker_compose_service="client",\n    image!=""\n  }[30s])\n)',
                "legend": "__auto",
            }
        ],
    },
    {
        "title": "Vendor Network (KiB/s)",
        "section": "vendor_resources",
        "queries": [
            {
                "promql": 'sum(\n  rate(container_network_receive_bytes_total{\n    job="cadvisor",\n    container_label_com_docker_compose_service="vendor",\n    image!=""\n  }[30s])\n) / 1024',
                "legend": "Input",
            },
            {
                "promql": 'sum(\n  rate(container_network_transmit_bytes_total{\n    job="cadvisor",\n    container_label_com_docker_compose_service="vendor",\n    image!=""\n  }[30s])\n) / 1024',
                "legend": "Output",
            },
        ],
    },
    {
        "title": "Vendor Memory Usage (MiB)",
        "section": "vendor_resources",
        "queries": [
            {
                "promql": 'sum(\n  container_memory_usage_bytes{\n    job="cadvisor",\n    container_label_com_docker_compose_service="vendor",\n    image!=""\n  }\n) / 1024 / 1024',
                "legend": "__auto",
            }
        ],
    },
    {
        "title": "Vendor CPU Usage (Cores)",
        "section": "vendor_resources",
        "queries": [
            {
                "promql": 'sum(\n  rate(container_cpu_usage_seconds_total{\n    job="cadvisor",\n    container_label_com_docker_compose_service="vendor",\n    image!=""\n  }[30s])\n)',
                "legend": "__auto",
            }
        ],
    },
    {
        "title": "Vendor Redis Memory Usage (MiB)",
        "section": "vendor_resources",
        "queries": [
            {
                "promql": 'container_memory_working_set_bytes{container_label_com_docker_compose_service="redis-vendor", image!=""} / 1024 / 1024',
                "legend": "Redis Vendor Memory",
            }
        ],
    },
    {
        "title": "Vendor Redis CPU Usage (Cores)",
        "section": "vendor_resources",
        "queries": [
            {
                "promql": 'rate(container_cpu_usage_seconds_total{job="cadvisor", name="nanomoni-redis-vendor-1", image!=""}[30s])',
                "legend": "Redis Vendor CPU",
            }
        ],
    },
]


def get_common_charts() -> List[Dict[str, Any]]:
    """Return common charts shared across all payment modes."""
    return COMMON_CHARTS
