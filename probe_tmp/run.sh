set -x
for i in 1 2 3 4 5; do python nhl_data.py probe_tmp/nhl_hist.json.gz; done
ls -la probe_tmp
