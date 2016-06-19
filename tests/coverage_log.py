import json
import pylab
import argparse
import subprocess as sp
from datetime import datetime

def get_args():
    """Read and parse arguments"""

    parser = argparse.ArgumentParser()

    parser.add_argument("-c", "--collect",
            help="Collect statistics. Default: print statistics.",
            action="store_true",
            default=False)


    return parser.parse_args()


# Plot line types:
styles = {
    "gipsync": [ "ro:", "r-" ], # style for total, style for covered
    "libgipsync/classes": [ "go:", "g-" ],
    "libgipsync/core": [ "bo:", "b-" ],
}

# Parse command-line arguments:
o = get_args()

# Read saved log:
logfn = "tests/coverage_log.json"
with open(logfn) as f:
    J = json.load(f)

# Collect data if requested:
if o.collect:
    # Get time:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Run tests:
    cmd = 'coverage run --source="." -m unittest discover -v'
    #s = sp.Popen(cmd, shell=True)
    #s.communicate()

    # Collect stats:
    for modname in J:
        cmd = "coverage report -m {mod}.py".format(mod=modname)
        s = sp.Popen(cmd, stdout=sp.PIPE, shell=True)
        out, err = s.communicate()
        tot, miss = [ int(x) for x in out.split("\n")[-2].split()[1:3] ]
        J[modname][now] = [ tot, tot -  miss]

    # Save collected data:
    with open(logfn, "w") as f:
        json.dump(J, f, indent=4)

# Plot, regardless:
fig = pylab.figure(0, figsize=(16,9))

xmin, xmax = None, None
for modname in J:
    X = [ datetime.strptime(x, "%Y-%m-%d %H:%M") for x in sorted(J[modname]) ]
    Ytotal = [ J[modname][x][0] for x in sorted(J[modname]) ]
    Ycovered = [ J[modname][x][1] for x in sorted(J[modname]) ]
    try:
        stot, scov = styles[modname]
    except:
        stot, scov = "o-", "o-"
    pylab.plot(X, Ytotal, stot, label="{m} (total)".format(m=modname))
    pylab.plot(X, Ycovered, scov, label="{m} (covered)".format(m=modname))

    if not xmin or X and X[0] < xmin:
        xmin = X[0]

    if not xmax or X and X[-1] < xmax:
        xmax = X[-1]

# Set options and show plot:
fig.autofmt_xdate()
pylab.xlabel("Date")
pylab.ylabel("LOC")
pylab.legend(bbox_to_anchor=(0.05, 0.95), loc=2, borderaxespad=0.5)
pylab.subplots_adjust(left=0.07, right=0.95, top=0.95, bottom=0.15)
pylab.show()
