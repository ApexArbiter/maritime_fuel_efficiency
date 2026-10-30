#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "FleetShip.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UWaterBodyComponent;

UENUM()
enum class EFleetShipType : uint8
{
	Container,
	Tanker,
	Bulker
};

UCLASS()
class MARITIMEFUELEFFICIENCY_API AFleetShip : public APawn
{
	GENERATED_BODY()

public:
	AFleetShip();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	void Configure(EFleetShipType InType, const TArray<FVector>& InWaypoints, float InInitialYawDegrees, float InInitialSurgeCms);
	void UpdateAutopilot(float DeltaSeconds);
	void ApplyMotion(float DeltaSeconds, float InSurgeCms, float InSwayCms, float InYawRate, float InYawDeg, float InHeaveCm, float InPitchDeg, float InRollDeg, float InFuelTonnesPerHour);
	void ResetVoyage();

	EFleetShipType GetShipType() const { return ShipType; }
	const FString& GetShipName() const { return ShipName; }
	float GetSpeedKnots() const { return SpeedKnots; }
	float GetHeadingDegrees() const { return YawDeg; }
	float GetRudderDegrees() const { return RudderDeg; }
	float GetHeaveMeters() const { return HeaveCm / 100.f; }
	float GetPitchDegrees() const { return PitchDeg; }
	float GetLeewayDegrees() const { return LeewayDeg; }
	float GetDistanceRemainingMeters() const { return DistanceRemainingM; }
	float GetFuelTonnesPerHour() const { return FuelTonnesPerHour; }
	float GetFuelRemainingTonnes() const { return FuelRemainingTonnes; }
	FVector GetRouteOrigin() const { return RouteOrigin; }
	const TArray<FVector>& GetWaypoints() const { return Waypoints; }
	int32 GetWaypointIndex() const { return WaypointIndex; }
	float GetDesiredSpeedMs() const { return DesiredMs; }
	float GetMassKg() const { return MassKg; }
	float GetLengthCm() const { return LengthCm; }
	float GetBeamCm() const { return BeamCm; }
	float GetDraftCm() const { return DraftCm; }
	float GetFreeboardCm() const { return FreeboardCm; }
	float GetEnginePowerW() const { return EnginePowerW; }
	float GetWettedAreaM2() const { return WettedM2; }
	float GetFrontalAreaM2() const { return FrontalAreaM2; }
	float GetLateralAreaM2() const { return LateralAreaM2; }
	float GetServiceCms() const { return ServiceMs * 100.f; }
	float GetSurgeCms() const { return SurgeCms; }
	float GetSwayCms() const { return SwayCms; }
	float GetYawRate() const { return YawRateRad; }

private:
	struct FShipSpec
	{
		const TCHAR* Name;
		float LengthM;
		float BeamM;
		float DraftM;
		float FreeboardM;
		float DisplacementT;
		float EnginePowerW;
		float ServiceKn;
	};

	static const FShipSpec& SpecFor(EFleetShipType Type);
	void BuildVisuals();
	void AddBox(const FVector& LocationCm, const FVector& SizeCm, const FLinearColor& Color, bool bCastShadow = true);
	UStaticMeshComponent* AddShape(UStaticMesh* Mesh, const FVector& LocationCm, const FRotator& Rotation, const FVector& Scale, const FLinearColor& Color, bool bCastShadow);
	void UpdateWake();
	UMaterialInstanceDynamic* MaterialFor(const FLinearColor& Color);
	bool SampleWater(const FVector& WorldLocation, float& OutSurfaceZ, FVector& OutVelocity) const;
	static float WrapDegrees(float Degrees);

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<USceneComponent> Root;

	UPROPERTY()
	TObjectPtr<UStaticMesh> CubeMesh;

	UPROPERTY()
	TObjectPtr<UStaticMesh> CylinderMesh;

	UPROPERTY()
	TObjectPtr<UStaticMesh> SphereMesh;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> BaseMaterial;

	UPROPERTY()
	TArray<TObjectPtr<UMaterialInstanceDynamic>> SharedMaterials;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> WakeParts;

	TArray<FLinearColor> SharedColors;

	EFleetShipType ShipType = EFleetShipType::Container;
	TArray<FVector> Waypoints;
	int32 WaypointIndex = 0;
	int32 BoxSerial = 0;

	FString ShipName;
	float LengthCm = 30000.f;
	float BeamCm = 4000.f;
	float DraftCm = 1450.f;
	float FreeboardCm = 800.f;
	float MassKg = 1.45e8f;
	float EnginePowerW = 4.57e7f;
	float ServiceMs = 11.6f;
	float WettedM2 = 18000.f;
	float LateralAreaM2 = 2400.f;
	float FrontalAreaM2 = 340.f;

	float YawDeg = 0.f;
	float InitialYawDeg = 0.f;
	float InitialSurgeCms = 450.f;
	float DesiredMs = 6.f;
	float SurgeCms = 500.f;
	float SwayCms = 0.f;
	float YawRateRad = 0.f;
	float HeaveCm = 0.f;
	float HeaveVel = 0.f;
	float PitchDeg = 0.f;
	float PitchVel = 0.f;
	float RollDeg = 0.f;
	float RollVel = 0.f;
	float RudderDeg = 0.f;
	float SpeedKnots = 0.f;
	float LeewayDeg = 0.f;
	float DistanceRemainingM = 0.f;
	float FuelTonnesPerHour = 0.f;
	float FuelRemainingTonnes = 0.f;
	FVector RouteOrigin = FVector::ZeroVector;
	bool bRouteOriginSet = false;

	TWeakObjectPtr<UWaterBodyComponent> OceanBody;
};
