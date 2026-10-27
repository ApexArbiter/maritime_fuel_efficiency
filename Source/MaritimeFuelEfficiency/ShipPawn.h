#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "ShipPawn.generated.h"

class UBuoyancyComponent;
class UStaticMeshComponent;
class FSocket;

UCLASS()
class MARITIMEFUELEFFICIENCY_API AShipPawn : public APawn
{
	GENERATED_BODY()

public:
	AShipPawn();

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	UBuoyancyComponent* GetBuoyancy() const { return Buoyancy; }
	UStaticMeshComponent* GetHull() const { return Hull; }

private:
	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UStaticMeshComponent> Hull;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UBuoyancyComponent> Buoyancy;

	FSocket* BridgeSocket = nullptr;
};
