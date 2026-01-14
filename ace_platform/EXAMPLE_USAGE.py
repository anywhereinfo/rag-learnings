from ace_platform.engine.loop import ACELoop

# --- 1. The Team Defines their "Plugin" ---
class TerraformGeneratorPlugin:
    def ingest(self, source_path):
        print(f"Reading Architecture Diagram from {source_path}...")
        # Custom Logic: Use Vision Model to read AWS diagram
        return "Context: 3 EC2 Instances, 1 RDS, VPC with 2 Subnets"

    def initial_playbook(self):
        return "- Use 'aws' provider version > 4.0\n- Tag all resources"

    def generate(self, context, playbook):
        print("Generating Terraform code...")
        # Custom Prompt specific to Terraform
        prompt = f"Write main.tf for: {context}. Rules: {playbook}"
        # call_llm(prompt)...
        return "resource 'aws_instance' 'web' { ... }"

    def reflect(self, artifact):
        print("Running 'terraform validate'...")
        # Custom Logic: Run CLI tool
        # import subprocess; subprocess.run("terraform validate")
        return "Error: Missing required argument 'ami'"

    def curate(self, playbook, critique):
        print("Learning from Validator errors...")
        new_rule = "- Always specify AMI ID for EC2 instances"
        return playbook + "\n" + new_rule

# --- 2. The Team Runs the Engine ---
if __name__ == "__main__":
    # The Team doesn't write the loop logic. They just use the Engine.
    plugin = TerraformGeneratorPlugin()
    
    engine = ACELoop(agent_config={'epochs': 3}, plugin=plugin)
    
    final_code = engine.run(input_data="docs/arch_diagram.png")
    
    print("\nFinal Terraform Code:")
    print(final_code)
