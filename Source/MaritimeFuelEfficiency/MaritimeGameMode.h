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

	virtual void BeginPlay() override;

private:
	void BuildOcean();
	void PinMapAndSun();
	void SpawnShipIfNeeded();
};
