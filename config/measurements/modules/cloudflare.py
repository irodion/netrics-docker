"""Measure Internet bandwidth and latency via Cloudflare's speed test."""
import subprocess as sp
import json

from schema import Optional, Or
from netrics import task
from .common import require_net

PARAMS = task.schema.extend('cloudflare', {
    # timeout: seconds after which test is canceled
    Optional('timeout', default=60): Or(task.schema.GTZero(),
                                        task.schema.falsey,
                                        error='timeout: seconds greater than zero or '
                                              'falsey to disable'),
    
    # output_bps: show speeds in bits per second instead of bytes
    Optional('output_bps', default=False): task.schema.BoolType(
        error='output_bps: must be a boolean (true/false)'
    ),
    
    # debug: enable debug logging for network I/O
    Optional('debug', default=False): task.schema.BoolType(
        error='debug: must be a boolean (true/false)'
    ),
})

@task.param.require(PARAMS)
@require_net
def main(params):
    """Run Cloudflare speed test and parse results."""
    
    # Construct command
    cmd = ['cfspeedtest', '--json']
    
    if params.output_bps:
        cmd.append('--bps')
    
    if params.debug:
        cmd.append('--debug')
    
    try:
        proc = sp.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=params.timeout if params.timeout else None
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
    
    # Check for command execution errors
    if proc.returncode != 0:
        task.log.critical(
            status=f'Error ({proc.returncode})',
            stdout=proc.stdout,
            stderr=proc.stderr,
            msg="cloudflare test failed",
        )
        return task.status.software_error
    
    # Parse JSON output
    try:
        results = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        task.log.critical(
            status='JSON parse error',
            stdout=proc.stdout,
            stderr=proc.stderr,
            msg=str(exc),
        )
        return task.status.software_error
    
    # Log summary information
    task.log.info(
        download_mbps=results.get('downloadSpeed'),
        upload_mbps=results.get('uploadSpeed'),
        latency_ms=results.get('latency'),
        jitter_ms=results.get('jitter'),
        isp=results.get('isp'),
        location=f"{results.get('city')}, {results.get('region')}",
        server=results.get('server'),
    )
    
    # Structure results for storage
    data = {
        'download': results.get('downloadSpeed'),        # Mbps
        'upload': results.get('uploadSpeed'),            # Mbps
        'latency': results.get('latency'),              # ms
        'jitter': results.get('jitter'),                # ms
        'ip': results.get('ip'),
        'isp': results.get('isp'),
        'location': {
            'city': results.get('city'),
            'region': results.get('region'),
            'country': results.get('country'),
            'colo': results.get('colo'),                # Cloudflare data center
        },
        'server': results.get('server'),
        'test_id': results.get('testId'),
        'timestamp': results.get('timestamp'),
    }
    
    # Format results based on configuration
    if params.result.flat:
        results = {f'speedtest_cloudflare_{feature}': value
                   for (feature, value) in data.items()}
    else:
        results = {'speedtest_cloudflare': data}
    
    # Write results
    task.result.write(results,
                      label=params.result.label,
                      annotate=params.result.annotate)
    
    return task.status.success


if __name__ == '__main__':
    main()