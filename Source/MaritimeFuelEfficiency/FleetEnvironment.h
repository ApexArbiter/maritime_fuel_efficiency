#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "HAL/PlatformProcess.h"
#include "IPAddress.h"
#include "FleetEnvironment.generated.h"

class FSocket;
class FInternetAddr;
class UProceduralMeshComponent;

UCLASS()
class MARITIMEFUELEFFICIENCY_API AFleetEnvironment : public AActor
{
	GENERATED_BODY()

public:
	AFleetEnvironment();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	void SetTimeScale(float Scale);
	void TogglePause();
	void StartSimulation();
	void ResetSimulation();
	void ApplyPreset(int32 Index);
	void NudgeWindSpeed(float DeltaMs);
	void NudgeWindDirection(float DeltaDeg);
	void NudgeCurrentSpeed(float DeltaMs);
	void NudgeCurrentDirection(float DeltaDeg);
	void NudgeWaveHeight(float DeltaM);
	void NudgeWaveDirection(float DeltaDeg);
	void NudgeHour(float DeltaHours);
	void ToggleDayNightCycle();
	void SetVisualSea(int32 Index);

	const FString& GetVisualSeaName() const { return VisualSeaName; }

	const FString& GetPresetName() const { return PresetName; }
	float GetTimeScale() const { return TimeScale; }
	bool IsPaused() const { return bPaused; }
	float GetHour() const { return Hour; }
	float GetWindSpeedMs() const { return WindMs; }
	float GetWindDirectionDeg() const { return WindDeg; }
	float GetCurrentSpeedMs() const { return CurrentMs; }
	float GetCurrentDirectionDeg() const { return CurrentDeg; }
	float GetWaveHeightM() const { return WaveM; }
	float GetWaveDirectionDeg() const { return WaveDeg; }
	float GetSimTime() const { return SimTime; }
	float GetAppliedWindMs() const { return AppliedWindMs; }
	float GetAppliedWindDirectionDeg() const { return AppliedWindDeg; }
	float GetAppliedCurrentMs() const { return AppliedCurrentMs; }
	float GetAppliedCurrentDirectionDeg() const { return AppliedCurrentDeg; }
	float GetAppliedWaveHeightM() const { return AppliedWaveM; }
	float GetAppliedWaveDirectionDeg() const { return AppliedWaveDeg; }
	bool HasPhysicsAck() const { return bPhysicsAck; }
	bool WasCommandRejected() const { return bCommandRejected; }
	bool IsPhysicsConnected() const { return bPhysicsConnected; }
	bool IsDayNightCycle() const { return bDayNight; }

private:
	void BindControls();
	void Time1() { SetTimeScale(1.f); }
	void Time5() { SetTimeScale(5.f); }
	void Time10() { SetTimeScale(10.f); }
	void Time20() { SetTimeScale(20.f); }
	void Preset0() { ApplyPreset(0); }
	void Preset1() { ApplyPreset(1); }
	void Preset2() { ApplyPreset(2); }
	void Preset3() { ApplyPreset(3); }
	void WindFaster() { NudgeWindSpeed(1.f); }
	void WindSlower() { NudgeWindSpeed(-1.f); }
	void WindLeft() { NudgeWindDirection(-10.f); }
	void WindRight() { NudgeWindDirection(10.f); }
	void CurrentFaster() { NudgeCurrentSpeed(0.2f); }
	void CurrentSlower() { NudgeCurrentSpeed(-0.2f); }
	void CurrentLeft() { NudgeCurrentDirection(-10.f); }
	void CurrentRight() { NudgeCurrentDirection(10.f); }
	void WavesHigher() { NudgeWaveHeight(0.4f); }
	void WavesLower() { NudgeWaveHeight(-0.4f); }
	void WavesLeft() { NudgeWaveDirection(-10.f); }
	void WavesRight() { NudgeWaveDirection(10.f); }
	void VisualCalm() { SetVisualSea(0); }
	void VisualModerate() { SetVisualSea(1); }
	void VisualRough() { SetVisualSea(2); }
	void HourLater() { NudgeHour(1.f); }
	void HourEarlier() { NudgeHour(-1.f); }
	void LaunchPhysics();
	void ApplySeaToWorld();
	void ApplySun();
	void StyleOceanSurface();
	void BuildVisualSea();
	void UpdateVisualSea();
	void ExchangePhysics(float DeltaSeconds);
	void RunControlDemo(float RealDt);
	void LogControlShip(const TCHAR* Label) const;
	void TrackVoyage(float DeltaSeconds);
	void MarkCustom();

	FString PresetName;
	float TimeScale = 1.f;
	float ResumeScale = 1.f;
	bool bPaused = false;
	bool bDayNight = false;
	bool bEnvDemo = false;
	bool bVoyageCompare = false;
	float Hour = 13.f;
	int32 Month = 6;
	float WindMs = 4.f;
	float WindDeg = 30.f;
	float CurrentMs = 0.25f;
	float CurrentDeg = 40.f;
	float WaveM = 0.4f;
	float WaveDeg = 30.f;
	int32 VisualSea = 1;
	FString VisualSeaName = TEXT("moderate visual");
	float SunLux = 12.f;
	float ExposureBias = 0.2f;
	FLinearColor SunColor = FLinearColor::White;
	float SimTime = 0.f;
	float DemoAccum = 0.f;
	int32 PresetIndex = 0;
	double LastRealSeconds = 0.0;
	uint32 PacketSeq = 1;
	bool bOceanStyled = false;
	bool bVisualSeaReady = false;
	int32 VisualSeaResolution = 128;

	UPROPERTY()
	TObjectPtr<UProceduralMeshComponent> VisualSeaMesh;

	TArray<FVector2D> VisualSeaXY;
	TArray<int32> VisualSeaTriangles;
	TArray<FVector> VisualSeaVertices;
	TArray<FVector> VisualSeaNormals;
	TArray<FVector2D> VisualSeaUV;
	TArray<FColor> VisualSeaColors;
	int32 OceanStyleAttempts = 0;
	bool bPhysicsConnected = false;
	bool bPhysicsAck = false;
	bool bCommandRejected = false;
	bool bControlDemo = false;
	float ControlDemoTime = 0.f;
	int32 ControlDemoStage = 0;
	float AppliedWindMs = 4.f;
	float AppliedWindDeg = 30.f;
	float AppliedCurrentMs = 0.25f;
	float AppliedCurrentDeg = 40.f;
	float AppliedWaveM = 0.4f;
	float AppliedWaveDeg = 30.f;
	bool bLoggedDisconnect = false;
	int32 MissedReplies = 0;

	FSocket* PhysicsSocket = nullptr;
	TSharedPtr<FInternetAddr> PhysicsAddress;
	FProcHandle PhysicsHandle;
	uint32 PhysicsPid = 0;
};
