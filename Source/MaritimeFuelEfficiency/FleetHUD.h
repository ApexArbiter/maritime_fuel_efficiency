#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "FleetHUD.generated.h"

UCLASS()
class MARITIMEFUELEFFICIENCY_API AFleetHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;
	virtual void NotifyHitBoxClick(FName BoxName) override;

private:
	void DrawWorldLine(const FVector& Start, const FVector& End, const FLinearColor& Color);
	void DrawCommand(float X, float Y, float W, float H, const FString& Label, FName BoxName);
};
