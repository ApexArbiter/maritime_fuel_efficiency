using UnrealBuildTool;

public class MaritimeFuelEfficiency : ModuleRules
{
	public MaritimeFuelEfficiency(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore"
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Water",
			"Buoyancy",
			"GeoReferencing",
			"SunPosition",
			"Sockets",
			"Networking"
		});
	}
}
