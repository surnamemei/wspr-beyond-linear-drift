# Runtime

Default Python interpreter for ML/research work:

/home/mei/global-python/bin/python

Do not use:
/usr/bin/python3

For GPU workloads, verify before long runs:

/home/mei/global-python/bin/python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"

If CUDA is unavailable, stop instead of falling back to CPU.