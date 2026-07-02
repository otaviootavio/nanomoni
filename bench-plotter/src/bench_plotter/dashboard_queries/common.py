#!/usr/bin/env python3
"""Common dashboard queries shared across all payment modes."""

# Common resource panels (issuer, client, vendor) that apply to all payment modes
COMMON_PANELS = [
    # Row: Issuer Resources
    {"title": "Issuer Resources", "type": "row", "section": "issuer_resources"},

    {
        "title": "Issuer Network (KiB/s)",
        "type": "timeseries",
        "section": "issuer_resources",
        "targets": [
            {
                "expr": "sum by (name) (\n  rate(container_network_receive_bytes_total{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"issuer\",\n    image!=\"\"\n  }[1m])\n) / 1024",
                "legendFormat": "Input",
            },
            {
                "expr": "sum by (name) (\n  rate(container_network_transmit_bytes_total{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"issuer\",\n    image!=\"\"\n  }[1m])\n) / 1024",
                "legendFormat": "Output",
            },
        ],
    },

    {
        "title": "Issuer Memory Usage (MiB)",
        "type": "timeseries",
        "section": "issuer_resources",
        "targets": [
            {
                "expr": "sum by (name) (\n  container_memory_usage_bytes{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"issuer\",\n    image!=\"\"\n  }\n) / 1024 / 1024",
                "legendFormat": "__auto",
            }
        ],
    },

    {
        "title": "Issuer CPU Usage (Cores)",
        "type": "timeseries",
        "section": "issuer_resources",
        "targets": [
            {
                "expr": "sum by (name) (\n  rate(container_cpu_usage_seconds_total{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"issuer\",\n    image!=\"\"\n  }[1m])\n)",
                "legendFormat": "__auto",
            }
        ],
    },

    {
        "title": "Issuer Redis Memory Usage (MiB)",
        "type": "timeseries",
        "section": "issuer_resources",
        "targets": [
            {
                "expr": "container_memory_working_set_bytes{container_label_com_docker_compose_service=\"redis-issuer\", image!=\"\"} / 1024 / 1024",
                "legendFormat": "Redis Issuer Memory",
            }
        ],
    },

    {
        "title": "Issuer Redis CPU Usage (Cores)",
        "type": "timeseries",
        "section": "issuer_resources",
        "targets": [
            {
                "expr": "rate(container_cpu_usage_seconds_total{job=\"cadvisor\", name=\"nanomoni-redis-issuer-1\", image!=\"\"}[1m])",
                "legendFormat": "Redis Issuer CPU",
            }
        ],
    },

    # Row: Client Resources
    {"title": "Client Resources", "type": "row", "section": "client_resources"},

    {
        "title": "Client Network (KiB/s)",
        "type": "timeseries",
        "section": "client_resources",
        "targets": [
            {
                "expr": "sum by (name) (\n  rate(container_network_receive_bytes_total{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"client\",\n    image!=\"\"\n  }[1m])\n) / 1024",
                "legendFormat": "Input",
            },
            {
                "expr": "sum by (name) (\n  rate(container_network_transmit_bytes_total{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"client\",\n    image!=\"\"\n  }[1m])\n) / 1024",
                "legendFormat": "Output",
            },
        ],
    },

    {
        "title": "Client Memory Usage (MiB)",
        "type": "timeseries",
        "section": "client_resources",
        "targets": [
            {
                "expr": "sum by (name) (\n  container_memory_usage_bytes{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"client\",\n    image!=\"\"\n  }\n) / 1024 / 1024",
                "legendFormat": "__auto",
            }
        ],
    },

    {
        "title": "Client CPU Usage (Cores)",
        "type": "timeseries",
        "section": "client_resources",
        "targets": [
            {
                "expr": "sum by (name) (\n  rate(container_cpu_usage_seconds_total{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"client\",\n    image!=\"\"\n  }[1m])\n)",
                "legendFormat": "__auto",
            }
        ],
    },

    # Row: Vendor Resources
    {"title": "Vendor Resources", "type": "row", "section": "vendor_resources"},

    {
        "title": "Vendor Network (KiB/s)",
        "type": "timeseries",
        "section": "vendor_resources",
        "targets": [
            {
                "expr": "sum by (name) (\n  rate(container_network_receive_bytes_total{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"vendor\",\n    image!=\"\"\n  }[1m])\n) / 1024",
                "legendFormat": "Input",
            },
            {
                "expr": "sum by (name) (\n  rate(container_network_transmit_bytes_total{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"vendor\",\n    image!=\"\"\n  }[1m])\n) / 1024",
                "legendFormat": "Output",
            },
        ],
    },

    {
        "title": "Vendor Memory Usage (MiB)",
        "type": "timeseries",
        "section": "vendor_resources",
        "targets": [
            {
                "expr": "sum by (name) (\n  container_memory_usage_bytes{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"vendor\",\n    image!=\"\"\n  }\n) / 1024 / 1024",
                "legendFormat": "__auto",
            }
        ],
    },

    {
        "title": "Vendor CPU Usage (Cores)",
        "type": "timeseries",
        "section": "vendor_resources",
        "targets": [
            {
                "expr": "sum by (name) (\n  rate(container_cpu_usage_seconds_total{\n    job=\"cadvisor\",\n    container_label_com_docker_compose_service=\"vendor\",\n    image!=\"\"\n  }[1m])\n)",
                "legendFormat": "__auto",
            }
        ],
    },

    {
        "title": "Vendor Redis Memory Usage (MiB)",
        "type": "timeseries",
        "section": "vendor_resources",
        "targets": [
            {
                "expr": "container_memory_working_set_bytes{container_label_com_docker_compose_service=\"redis-vendor\", image!=\"\"} / 1024 / 1024",
                "legendFormat": "Redis Vendor Memory",
            }
        ],
    },

    {
        "title": "Vendor Redis CPU Usage (Cores)",
        "type": "timeseries",
        "section": "vendor_resources",
        "targets": [
            {
                "expr": "rate(container_cpu_usage_seconds_total{job=\"cadvisor\", name=\"nanomoni-redis-vendor-1\", image!=\"\"}[1m])",
                "legendFormat": "Redis Vendor CPU",
            }
        ],
    },
]


def get_common_panels():
    """Return common panels shared across all payment modes."""
    return COMMON_PANELS
