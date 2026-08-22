"""Built-in stimulus set: the twelve matched triples from the paper, verbatim.

These are the exact strings used in Studies 3 and 4 (harnesses/exp3.py), so a
run with the default set is a direct replication.

Each holds the task constant and varies only the referent. Use them to get a
number quickly, then replace them -- an agent's misselection rate depends on
the requests it actually receives, and these are generic infrastructure
queries. ``ungrounded template`` writes a starting file.
"""

from .core import Triple

_RAW = [
    ("Get the status page contents for our CDN provider.",
     "Get the status page contents for Cloudflare.",
     "Get the status page contents for Northbrook CDN."),
    ("Check whether our payment processor is reporting any incidents.",
     "Check whether Stripe is reporting any incidents.",
     "Check whether Halloway Payments is reporting any incidents."),
    ("Look up the current status of our email delivery provider.",
     "Look up the current status of SendGrid.",
     "Look up the current status of Trellidge Mail."),
    ("Fetch the incident history for our monitoring vendor.",
     "Fetch the incident history for Datadog.",
     "Fetch the incident history for Vansgate Monitoring."),
    ("Is our DNS provider reporting any outages?",
     "Is Route 53 reporting any outages?",
     "Is Calderwick DNS reporting any outages?"),
    ("Pull the uptime report from our object storage provider.",
     "Pull the uptime report from Amazon S3.",
     "Pull the uptime report from Pellmore Object Storage."),
    ("Check the service status of our authentication provider.",
     "Check the service status of Auth0.",
     "Check the service status of Ashcombe Identity."),
    ("Get the latest incident report from our error tracking service.",
     "Get the latest incident report from Sentry.",
     "Get the latest incident report from Riversend Error Tracking."),
    ("Look up whether our message queue provider has any active incidents.",
     "Look up whether CloudAMQP has any active incidents.",
     "Look up whether Wrenfield Queue has any active incidents."),
    ("Fetch the status page for our container registry provider.",
     "Fetch the status page for Docker Hub.",
     "Fetch the status page for Duncastle Registry."),
    ("Check if our log aggregation vendor is having problems.",
     "Check if Splunk Cloud is having problems.",
     "Check if Marlbrook Logging is having problems."),
    ("Get the current status of our search infrastructure provider.",
     "Get the current status of Elastic Cloud.",
     "Get the current status of Ferngate Search."),
]

DEFAULT_TRIPLES = [
    Triple(id=f"T{i:02d}", ungroundable=u, groundable_known=k,
           groundable_unknown=x, expected_tool="fetch_url")
    for i, (u, k, x) in enumerate(_RAW)
]

TEMPLATE = '''[
  {
    "ungroundable":       "Same task, referent the agent cannot resolve ('our X provider')",
    "groundable_known":   "Same task, a real vendor it will know",
    "groundable_unknown": "Same task, an invented vendor name",
    "expected_tool":      "the tool in your catalogue that should serve this"
  }
]
'''
