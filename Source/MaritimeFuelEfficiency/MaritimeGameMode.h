#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "MaritimeGameMode.generated.h"

UCLASS()
class MARITIMEFUELEFFICIENCY_API AMaritimeGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AMaritimeGameMode();

	virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
	virtual void BeginPlay() override;

private:
	void BuildOcean();
	void PinMapAndSun();
	void SpawnShipIfNeeded();
	void SpawnFleet();
	void SpawnBeacon(const FVector& Location, const FLinearColor& Color, float HeightCm);
	void SpawnRoute(const FVector& From, const FVector& To, const FLinearColor& Color);

	bool bFleetDemo = false;
};
