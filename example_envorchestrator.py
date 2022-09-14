from veca.env_manager import EnvOrchestrator


if __name__ == "__main__":
    # Executing the Environment Orchestrator process at another server.
    env = EnvOrchestrator(
        port = 8872,        # Exposed port of Environment Orchestrator
        port_instance = 46490   # inter-process communication port with orchestrator and unity instances (localport ~ localport + num_envs)
        )