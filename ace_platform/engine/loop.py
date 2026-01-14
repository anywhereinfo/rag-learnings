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
        
        previous_critique_len = 0
        
        for i in range(self.epochs):
            print(f"\n=== Epoch {i+1} ===")
            
            # 2. Generate
            artifact = self.plugin.generate(context, playbook)
            
            # 3. Reflect
            critique = self.plugin.reflect(artifact, context)
            
            # Check for qualitative convergence
            if "NO_ISSUES" in critique:
                print("Converged! No issues found.")
                return artifact
            
            # Quantitative Convergence Check
            critique_len = len(critique)
            print(f"   Critique Length: {critique_len} chars")
            
            if previous_critique_len > 0:
                improvement = (previous_critique_len - critique_len) / previous_critique_len
                print(f"   Improvement vs last epoch: {round(improvement*100, 1)}%")
                
                # Only stop if improvement is POSITIVE but small (0-5%)
                # If negative (getting worse) or large (>5%), keep going
                if 0 < improvement < 0.05:
                    print("   !! Diminishing returns detected (0-5% improvement). Stopping early.")
                    break
                elif improvement <= 0:
                    print("   !! Critique size INCREASED. Agent needs more training - continuing...")
            
            previous_critique_len = critique_len
            
            # 4. Curate
            playbook = self.plugin.curate(playbook, critique)
            
            # Metrics
            playbook_rules_count = len([line for line in playbook.split('\n') if line.strip().startswith('-')])
            print(f"   [Epoch {i+1} Stats]: Critique Size={critique_len} chars | Playbook Rules={playbook_rules_count}")
            
        return artifact, playbook
