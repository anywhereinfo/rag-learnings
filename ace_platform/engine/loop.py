class ACELoop:
    def __init__(self, agent_config, plugin):
        self.epochs = agent_config.get('epochs', 3)
        self.plugin = plugin
        # Initialize components from config
        # self.llm = ...
        # self.memory = ...

    def run(self, input_data):
        print(f"Starting ACE Loop for {self.epochs} epochs...")
        
        # 1. Ingest
        context = self.plugin.ingest(input_data)
        playbook = self.plugin.initial_playbook()
        
        for i in range(self.epochs):
            print(f"=== Epoch {i+1} ===")
            
            # 2. Generate
            artifact = self.plugin.generate(context, playbook)
            
            # 3. Reflect
            critique = self.plugin.reflect(artifact, context)
            
            if "NO_ISSUES" in critique:
                print("Converged!")
                return artifact
            
            # 4. Curate
            playbook = self.plugin.curate(playbook, critique)
            
        return artifact
