#pragma once

#include "CoreMinimal.h"
#include "FleetShip.h"
#include "GameFramework/Pawn.h"
#include "FleetCameraPawn.generated.h"

class UCameraComponent;

UCLASS()
class MARITIMEFUELEFFICIENCY_API AFleetCameraPawn : public APawn
{
	GENERATED_BODY()

public:
	AFleetCameraPawn();

	virtual void Tick(float DeltaSeconds) override;

private:
	void TickFleetView();
	void TickPresentationShots(double NowSeconds);
	AFleetShip* FindShip(EFleetShipType Type) const;
	void FrameShip(const AFleetShip& Ship, int32 Kind);
	void CaptureShot(const AFleetShip& Ship, const TCHAR* Label);

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UCameraComponent> Camera;

	bool bPresentationShots = false;
	bool bPresentationClockStarted = false;
	int32 PresentationLeadFrames = 0;
	int32 PresentationShot = 0;
	int32 PresentationFrames = 0;
	int32 PresentationCaptures = 0;
	int32 FramesAfterLastShot = 0;
};
