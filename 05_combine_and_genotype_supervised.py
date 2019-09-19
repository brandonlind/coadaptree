"""
### usage
# python 03a_combine_and_genotype_by_pool.py parentdir
###

### fix
# create reservation file to streamline pipeline
# auto tune scheduler thresh to server
###
"""

### imports
import sys, balance_queue
from collections import Counter
from coadaptree import *
### 

### args
thisfile, parentdir = sys.argv
if parentdir.endswith("/"):
    parentdir = parentdir[:-1]
###

### reqs
poolref = pklload(op.join(parentdir, 'poolref.pkl'))  #key=pool val=/path/to/ref.fa
poolsamps = pklload(op.join(parentdir, 'poolsamps.pkl'))
pools = uni(list(poolsamps.keys()))
###

# get a list of subdirectory pool dirs created earlier in pipeline
pooldirs = []
for p in pools:
    pooldir = op.join(parentdir, p)
    if op.exists(pooldir):
        pooldirs.append(pooldir)

# get a list of files that have finished
finished = {}
for d in pooldirs:
    pool = op.basename(d)
    vcfdir = op.join(d, 'vcfs')
    finished[pool] = [f.replace(".gz.tbi", ".gz") for f in fs(vcfdir) if f.endswith('.gz.tbi')]

# create some dirs
outdir = op.join(parentdir, 'snps')
shdir  = op.join(parentdir, 'shfiles/select_variants')
createdirs([outdir,shdir])

# get a list of snpfiles that have already been made
snpfiles = [f.replace(".tbi","") for f in fs(outdir) if 'snps' in op.basename(f) and f.endswith('.tbi')]
print('len(snpfiles) = ',len(snpfiles))

# make sh files
alreadycreated = [f for f in fs(shdir) if f.endswith('.sh') and 'swp' not in f]
print('len(alreadycreated) = ', len(alreadycreated))
newfiles = Counter()
shfiles = []
for pool,files in finished.items():
    thresh = len(poolsamps[pool])
    # get the files that need to be combined across samples (by interval/scaff)
    groups = {}
    for f in files:
        scaff = op.basename(f).split("scatter")[1].split(".g.v")[0]
        if scaff not in groups:
            groups[scaff] = []
        groups[scaff].append(f)
    for scaff,sfiles in groups.items():
        cmds = ''''''
        combfile = op.join(outdir, f"{pool}--{scaff}_combined.vcf.gz")
        gfile = combfile.replace("_combined.vcf.gz", "_genotyped.vcf.gz")
        snpfile = gfile.replace("_genotyped.vcf.gz", "_snps.vcf.gz")
        if snpfile in snpfiles:
            # if the snpfile has already been made, move on to the next
            continue
        if len(sfiles) == thresh:
            # if the number of gvcf.tbi files created match the number of samps (expected number):
            if thresh > 1:
                # if we need to combine across samps:
                varcmd = '--variant ' + ' --variant '.join([x for x in sorted(sfiles)])
                combinestep = f'''echo COMBINING GVCFs
gatk CombineGVCFs -R {ref} {varcmd} -O {combfile}
'''
            else:
                # if there is only one samp: len(sfiles) == 1 == thresh
                combinestep = ''''''
                combfile = sfiles[0]
            # create rest of commands
            cmds = f'''{combinestep}
echo GENOTYPING GVCFs
gatk GenotypeGVCFs -R {ref} -V {combfile} -O {gfile} 

echo SELECTING VARIANTS
gatk SelectVariants -R {ref} -V {gfile} --select-type-to-include SNP -O {snpfile}

'''
        else:
            # if not all expected files have been made, print what's missing
            missing = thresh - len(groups[scaff])
            print('\t', pool, scaff, f'doesnt have enough files, missing {missing} files.')
            continue
        
        file = op.join(shdir, f'genotype---{pool}---{scaff}.sh')
        if file not in alreadycreated:
            newfiles[pool] += 1
            text = f'''#!/bin/bash
#SBATCH --time=11:59:00
#SBATCH --ntasks=1
#SBATCH --mem=4000M
#SBATCH --cpus-per-task=1
#SBATCH --job-name=genotype---{pool}---{scaff}
#SBATCH --output=genotype---{pool}---{scaff}---%j.out 

export _JAVA_OPTIONS="-Xms256m -Xmx3g"

source $HOME/.bashrc
export PYTHONPATH="${{PYTHONPATH}}:$HOME/gatk_pipeline"
export SQUEUE_FORMAT="%.8i %.8u %.12a %.68j %.3t %16S %.10L %.5D %.4C %.6b %.7m %N (%r)"

cat $0
# next line necessary for rescheduler
echo shfile = {file}

# requeue jobs with errors
python $HOME/gatk_pipeline/genotyping_rescheduler.py {parentdir}

# fill up the queue
python $HOME/gatk_pipeline/genotyping_scheduler.py {parentdir}

# genotype current file
module load gatk/4.1.0.0
{cmds}

# keep running jobs until time runs out
echo getting help from genotyping_helper
# python $HOME/gatk_pipeline/genotyping_helper.py {parentdir} {snpfile}

# in case there's time, schedule the next batch
python $HOME/gatk_pipeline/05_combine_and_genotype_supervised.py {parentdir}

'''
            with open(file, 'w') as o:
                o.write("%s" % text)
            shfiles.append(file)

# create scheddir queue
scheddir = op.join(parentdir, 'shfiles/supervised/select_variants')
if not op.exists(scheddir):
    os.makedirs(scheddir)
    
for pool in newfiles:
    print(pool,' created ', newfiles[pool],' files')
    
for sh in shfiles:
    dst = op.join(scheddir, op.basename(sh))
    try:
        os.symlink(sh, dst)
    except:
        print('could not create symlink')
        
# # submit to scheduler, balance accounts
os.system(f'python $HOME/gatk_pipeline/genotyping_scheduler.py {parentdir}')

print(shdir, len( fs(shdir) ) )

# balance queue
balance_queue.main('balance_queue.py', 'genotype', parentdir)