"""
### usage
# python 04_scatter-gvcf.py dupfile pooldir ref samp
###

### purpose
# use intervals.list files (created outside of the pipeline) to parallelize HaplotypeCaller calls
###
"""

import sys, subprocess
from coadaptree import *

### args
thisfile, dupfile, pooldir, samp = sys.argv
### 

print ('pooldir =', pooldir)

# info
parentdir = op.dirname(pooldir)
pool = op.basename(pooldir) 
ref = pklload(op.join(parentdir, 'poolref.pkl'))[pool]
bash_variables = op.join(parentdir, 'bash_variables')

# create dirs
shdir = op.join(pooldir, 'shfiles')
gvcfdir = op.join(shdir, '04_gvcf_shfiles')
vcfdir = op.join(pooldir, 'vcfs')
scheddir = op.join(parentdir, 'shfiles/gvcf_shfiles')
for d in [shdir, gvcfdir, vcfdir, scheddir]:
    makedir(d)

# create filenames
dupdir = op.dirname(dupfile)
rawvcf = op.join(vcfdir, f'raw_{pool}-{samp}.g.vcf.gz')

#get ploidy 
ploidy = int(pklload(op.join(parentdir, 'ploidy.pkl'))[samp])
print ('ploidy =', ploidy)

# create sh files
shfiles = []
shcount = 0
if ploidy > 2: #poolseq
    print ("this is a poolseq file")
else:
    print ("this is an individual's file")
scafdir = op.join(op.dirname(ref), 'intervals')
    
scaffiles = [f for f in fs(scafdir) if f.endswith('.list')]
os.system('echo found %s intervalfiles' % str(len(scaffiles)))
for scaff in scaffiles:
    s = "scatter-%s" % scaff.split(".list")[0].split("batch_")[1]
    filE = op.join(gvcfdir, f'{pool}-{samp}-{s}.sh')
    vcf = rawvcf.replace(".g.vcf.gz", "-%s.g.vcf.gz" % s)
    tbi = vcf.replace(".gz", ".gz.tbi")
    text = f'''#!/bin/bash
#SBATCH --time=11:59:00
#SBATCH --ntasks=1
#SBATCH --mem-per-cpu=20000M
#SBATCH --job-name={pool}-{samp}-{s}
#SBATCH --output={pool}-{samp}-{s}_%j.out 

# for debugging 
cat $0 
echo {filE}

source {bash_variables}

# resubmit jobs with errors
python $HOME/gatk_pipeline/rescheduler.py {pooldir}

# fill up the queue
python $HOME/gatk_pipeline/scheduler.py {pooldir}

# call variants
module load gatk/4.1.0.0
gatk HaplotypeCaller --sample-ploidy {ploidy} -R {ref} --genotyping-mode DISCOVERY -ERC GVCF -I {dupfile} -O {vcf} -L {scaff} --minimum-mapping-quality 20

# keep running jobs until time runs out
echo 'getting help from gvcf_helper'
python $HOME/gatk_pipeline/gvcf_helper.py {pooldir} {tbi}

# if finished running jobs, see if any can go on to the next stage (GenotypeGVCFs)
echo 'looking for GenotypeGVCF jobs'
python $HOME/gatk_pipeline/05_combine_and_genotype_supervised.py {parentdir}

'''
    with open(filE, 'w') as o:
        o.write("%s" % text)
    # now create a symlink in scheddir
    dst = op.join(scheddir, op.basename(filE))
    if not op.exists(dst):
        os.symlink(filE, dst)

# submit to scheduler
scheduler = op.join(os.environ['HOME'], 'gatk_pipeline/scheduler.py')
subprocess.call([sys.executable, scheduler, pooldir])
