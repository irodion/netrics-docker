"""Measure Internet bandwidth, *etc*., via Measurement Lab's NDT7 Client CLI."""
import subprocess as sp
import json

from schema import Optional, Or
from netrics import task
from .common import require_net

PARAMS = task.schema.extend('ndt7', {
    # exec: speedtest executable name or path
    Optional('exec', default='ndt7-client'): task.schema.Command(
        error='exec: must be an executable on PATH or file system absolute path to be executable'
    ),

    # timeout: seconds after which test is canceled
    # (0, None, False, etc. to disable timeout)
    Optional('timeout', default=60): Or(task.schema.GTZero(),
                                        task.schema.falsey,
                                        error='timeout: seconds greater than zero or '
                                              'falsey to disable'),
})

@task.param.require(PARAMS)
@require_net
def main(params):

    try:
        proc = sp.run(
            (
                params.exec,
                '-format', 'json',
            ),
            capture_output=True,
            text=True
        )

    except sp.TimeoutExpired as exc:
        task.log.critical(
            cmd=exc.cmd,
            elapsed=exc.timeout,
            stdout=exc.stdout,
            stderr=exc.stderr,
            status='timeout',
        )
        return task.status.timeout

    parsed = parse_output(proc.stdout)

    if not parsed:
        task.log.critical(
            status=f'Error ({proc.returncode})',
            stdout=proc.stdout,
            stderr=proc.stderr,
            msg="no results",
        )
        return task.status.no_host

    if proc.stderr:
        task.log.error(
            status=f'Error ({proc.returncode})',
            stdout=proc.stdout,
            stderr=proc.stderr,
            msg="results despite errors",
        )

    task.log.info(
        download=parsed['download'],
        upload=parsed['upload'],
        bytes_consumed=parsed['meta'].get('total_bytes_consumed'),
        downloaduuid=parsed['downloaduuid'],
    )

    # flatten results
    data = {key: value for (key, value) in parsed.items() if key != 'meta'}

    if params.result.flat:
        results = {f'speedtest_ndt7_{feature}': value
                   for (feature, value) in data.items()}

    else:
        results = {'speedtest_ndt7': data}

    # extend results with non-measurement data
    if 'total_bytes_consumed' in parsed['meta']:
        extended = {'test_bytes_consumed': parsed['meta']['total_bytes_consumed']}
    else:
        extended = None

    # write results
    task.result.write(results,
                      label=params.result.label,
                      annotate=params.result.annotate,
                      extend=extended)

    return task.status.success


def parse_output(output):

    if not output:
        return None
    
    dl_bytes = 0
    ul_bytes = 0
    result = None
    
    # Network quality metrics from TCPInfo
    tcp_metrics = {
        'rtt_var': None,         # RTT variance in microseconds
        'total_retrans': None,   # Total number of retransmissions
        'reord_seen': None,      # Number of reorder events seen
        'snd_buf_limited': None, # Send buffer limited events
        'pacing_rate': None,     # Pacing rate in bytes per second
        'delivery_rate': None,   # Delivery rate in bytes per second
        'min_rtt': None          # Minimum RTT in microseconds
    }
    
    try:
        for obj in output.split("\n")[:-1]:
            if not obj.strip():
                continue

            response = json.loads(obj)
            key = response.get("Key", None)
            value = response.get("Value", None)

            if key == "measurement":
                origin = value['Origin']
                test = value['Test']
                if origin == 'client':
                    num_bytes = value["AppInfo"]["NumBytes"]
                    if test == "download":
                        dl_bytes = num_bytes
                    else:
                        ul_bytes = num_bytes
                
                # Capture network quality metrics from server-side TCP info
                elif origin == 'server' and test == 'download' and 'TCPInfo' in value:
                    tcp_info = value['TCPInfo']
                    tcp_metrics['rtt_var'] = tcp_info.get('RTTVar')
                    tcp_metrics['total_retrans'] = tcp_info.get('TotalRetrans')
                    tcp_metrics['reord_seen'] = tcp_info.get('ReordSeen')
                    tcp_metrics['snd_buf_limited'] = tcp_info.get('SndBufLimited')
                    tcp_metrics['pacing_rate'] = tcp_info.get('PacingRate')
                    tcp_metrics['delivery_rate'] = tcp_info.get('DeliveryRate')
                    tcp_metrics['min_rtt'] = tcp_info.get('MinRTT')

            if (not key) and (not value):
                # Handle the actual NDT7 output format
                result = {
                    'download': response["Download"]["Throughput"]["Value"],
                    'upload': response["Upload"]["Throughput"]["Value"],
                    'downloadretrans': response["Download"]["Retransmission"]["Value"],
                    'minrtt': response["Download"]["Latency"]["Value"],
                    'server': response["ServerFQDN"],
                    'server_ip': response["ServerIP"],
                    'downloaduuid': response["Download"]["UUID"],
                    # Add network quality metrics
                    'rtt_var': tcp_metrics['rtt_var'],
                    'total_retrans': tcp_metrics['total_retrans'],
                    'reord_seen': tcp_metrics['reord_seen'],
                    'snd_buf_limited': tcp_metrics['snd_buf_limited'],
                    'pacing_rate': tcp_metrics['pacing_rate'],
                    'delivery_rate': tcp_metrics['delivery_rate'],
                    'tcp_min_rtt': tcp_metrics['min_rtt'],
                    'meta': {}
                }
    
    except (KeyError, ValueError, TypeError) as exc:
        print("output parsing error")
        return None
    
    if result:
        result["meta"]["total_bytes_consumed"] = dl_bytes + ul_bytes
        return result
    
    return None


if __name__ == '__main__':
    main()
