# 🧠 Cortex

A Streamlit-based interface for managing HPC neuroimaging workflows on Slurm clusters. Cortex provides project-scoped pipeline configuration and status monitoring, plus data download and visualization tools.

## Features

### 🔄 Workflows
- **Pipeline Configuration**: Select modules and resource allocations per project
- **Dependency Ordering**: Enforce upstream/downstream module relationships
- **Pipeline Status**: Monitor per-subject/session module states
- **Auto-trigger Compatible**: Saved configs are consumed by the external trigger script

### 📥 Download Data
- **Smart File Browser**: Navigate remote directories with an intuitive interface
- **Batch Downloads**: Download multiple files simultaneously
- **Auto-detection**: Automatically locate output files from your jobs
- **Progress Tracking**: Monitor download progress for large file transfers
- **Remote Directory Navigation**: Browse the HPC filesystem without command-line access

### 📊 Visualize Data
- **Interactive Plots**: Create dynamic visualizations of your results
- **Data Exploration**: Browse and analyze datasets directly in the browser
- **Export Options**: Save visualizations in multiple formats
- **Custom Dashboards**: Build personalized analytics views for your data

## Prerequisites

- Python 3.8 or higher
- SSH access to an HPC cluster running Slurm
- SSH key-based authentication configured
- Apptainer/Singularity installed on the HPC cluster (for container jobs)

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd hpc-slurm-job-manager
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure you have SSH key-based authentication set up for your HPC cluster:
```bash
ssh-keygen -t rsa -b 4096
ssh-copy-id username@your-hpc-cluster.edu
```

## Usage

### Starting the Application

1. Launch the Streamlit app:
```bash
streamlit run Home.py
```

2. Open your web browser and navigate to the URL displayed (typically `http://localhost:8501`)

### Connecting to Your HPC Cluster

1. In the sidebar, enter your connection details:
   - **Hostname**: Your HPC login node (e.g., `login1.your-cluster.edu`)
   - **Username**: Your HPC username
   - **SSH Key Path**: Path to your private SSH key (default: `~/.ssh/id_rsa`)

2. Click **Connect**

3. Once connected, you'll see a success message and can access all features

### Submitting Jobs

#### Configuring Workflows

1. Navigate to **Workflows**
2. Open **Pipeline Configuration**
3. Select modules and set resources (CPU, memory, GPU, time)
4. Save configuration for the selected project

#### Monitoring Pipeline Runs

1. Navigate to **Workflows**
2. Open **Pipeline Status**
3. Refresh status to poll Slurm and update manifest states

### Downloading Results

1. Navigate to **Download Data**
2. Browse the remote filesystem
3. Select files or directories to download
4. Choose local destination
5. Click **Download** and monitor progress

### Visualizing Data

1. Navigate to **Visualize Data**
2. Select or upload data files
3. Choose visualization type (plots, charts, tables)
4. Customize appearance and parameters
5. Export visualizations as needed

## Configuration

### Environment Variables

You can set default values using environment variables:

```bash
export HPC_HOSTNAME="login1.your-cluster.edu"
export HPC_USERNAME="your-username"
export HPC_SSH_KEY="~/.ssh/id_rsa"
```

### SSH Configuration

For easier connection, add your HPC cluster to `~/.ssh/config`:

```
Host hpc-cluster
    HostName login1.your-cluster.edu
    User your-username
    IdentityFile ~/.ssh/id_rsa
    ServerAliveInterval 60
```

## Project Structure

```
Cortex/
├── Home.py                  # Main entry + connection/auth UI
├── hpc_client_ssh.py        # SSH client wrapper for HPC operations
├── pages/
│   ├── 1_Workflows.py       # Pipeline configuration + status
│   ├── 2_Visualize_Data.py  # Data visualization tools
│   └── 3_Download_Data.py   # File download interface
├── scripts/
│   ├── cortex_trigger.py    # External auto-trigger script
│   └── cortex_trigger.sh    # Scheduler wrapper
├── utils/
│   ├── bids.py
│   ├── hpc_io.py
│   ├── modules.py
│   └── sidebar.py
└── README.md
```

## Dependencies

Key dependencies include:
- `streamlit` - Web application framework
- `paramiko` - SSH protocol implementation
- `pandas` - Data manipulation and analysis
- `plotly` / `matplotlib` - Data visualization
- Additional dependencies listed in `requirements.txt`

## Troubleshooting

### Connection Issues

**Problem**: Cannot connect to HPC cluster

**Solutions**:
- Verify hostname is correct and accessible
- Ensure SSH key has correct permissions (`chmod 600 ~/.ssh/id_rsa`)
- Test SSH connection manually: `ssh username@hostname`
- Check if SSH key is added to `~/.ssh/authorized_keys` on the cluster

### Job Submission Failures

**Problem**: Jobs fail to submit

**Solutions**:
- Verify Slurm is accessible: test with `sinfo` command on cluster
- Check resource requests don't exceed cluster limits
- Ensure container paths are correct and accessible
- Verify working directories exist and are writable

### Download Problems

**Problem**: File downloads fail or are slow

**Solutions**:
- Check network connectivity to HPC cluster
- Verify file permissions on remote system
- For large files, consider using batch download mode
- Ensure sufficient local disk space

## Security Considerations

- SSH keys are never transmitted or stored by the application
- All connections use SSH key-based authentication
- Session state is stored locally in the browser
- Disconnect from the cluster when not in use
- Use appropriate file permissions for SSH keys (`600`)

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues, questions, or feature requests:
- Check the documentation in each page of the application
- Review example workflows in the Workflow tab
- Open an issue on the project repository

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with:
- [Streamlit](https://streamlit.io/) - Web application framework
- [Paramiko](https://www.paramiko.org/) - SSH implementation
- [Slurm](https://slurm.schedmd.com/) - HPC workload manager
- [Apptainer](https://apptainer.org/) - Container platform

---

**Note**: This application is designed for use with Slurm-based HPC clusters. Ensure you have proper authorization and follow your institution's acceptable use policies when accessing HPC resources.
