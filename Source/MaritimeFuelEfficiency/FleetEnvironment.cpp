#include "FleetEnvironment.h"

#include "Components/LightComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/Engine.h"
#include "Components/SkyLightComponent.h"
#include "Engine/SkyLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "FleetShip.h"
#include "GerstnerWaterWaves.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "InputCoreTypes.h"
#include "GameFramework/PlayerController.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "SunPosition.h"
#include "WaterBodyComponent.h"
#include "WaterBodyOceanActor.h"
#include "WaterZoneActor.h"
#include "WaterMeshComponent.h"
#include "ProceduralMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
	struct FSeaPreset
	{
		const TCHAR* Name;
		int32 Month;
		float Hour;
		float WindMs;
		float WindDeg;
		float CurrentMs;
		float CurrentDeg;
		float WaveM;
		float WaveDeg;
		float Lux;
		float Exposure;
		FLinearColor SunColor;
	};

	const FSeaPreset Presets[] = {
		{ TEXT("summer calm"), 6, 13.f, 4.f, 30.f, 0.25f, 40.f, 0.4f, 30.f, 12.f, 0.25f, FLinearColor(1.f, 0.96f, 0.88f) },
		{ TEXT("spring tide"), 3, 9.f, 8.f, 110.f, 1.4f, 120.f, 1.3f, 110.f, 9.f, 0.05f, FLinearColor(0.95f, 0.97f, 1.f) },
		{ TEXT("autumn gale"), 9, 16.f, 18.f, 200.f, 0.7f, 190.f, 2.8f, 200.f, 5.f, -0.35f, FLinearColor(0.85f, 0.88f, 0.95f) },
		{ TEXT("winter storm"), 12, 20.5f, 22.f, 210.f, 1.2f, 130.f, 4.f, 200.f, 1.2f, -1.05f, FLinearColor(0.65f, 0.75f, 1.f) }
	};

	void AppendBytes(TArray<uint8>& Buffer, const void* Data, int32 Size)
	{
		const int32 Offset = Buffer.AddUninitialized(Size);
		FMemory::Memcpy(Buffer.GetData() + Offset, Data, Size);
	}

	template <typename T>
	void Append(TArray<uint8>& Buffer, T Value)
	{
		AppendBytes(Buffer, &Value, sizeof(T));
	}
}

AFleetEnvironment::AFleetEnvironment()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
}

void AFleetEnvironment::BeginPlay()
{
	Super::BeginPlay();
	bVoyageCompare = FParse::Param(FCommandLine::Get(), TEXT("VoyageCompare"));
	bEnvDemo = FParse::Param(FCommandLine::Get(), TEXT("EnvDemo")) && !bVoyageCompare;
	bControlDemo = FParse::Param(FCommandLine::Get(), TEXT("ControlDemo")) && !bVoyageCompare;
	LaunchPhysics();
	ApplyPreset(0);
	BuildVisualSea();
	if (bVoyageCompare)
	{
		SetTimeScale(8.f);
	}
	else if (bEnvDemo)
	{
		SetTimeScale(5.f);
	}
	BindControls();
	LastRealSeconds = FPlatformTime::Seconds();
	UE_LOG(LogTemp, Display, TEXT("ENV CONTROLS ready preset %s, time %.0fx, physics %s"),
		*PresetName, TimeScale, bPhysicsConnected ? TEXT("connected") : TEXT("waiting"));
}

void AFleetEnvironment::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (PhysicsSocket)
	{
		PhysicsSocket->Close();
		ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(PhysicsSocket);
		PhysicsSocket = nullptr;
	}
	if (PhysicsHandle.IsValid())
	{
		FPlatformProcess::TerminateProc(PhysicsHandle, true);
		FPlatformProcess::CloseProc(PhysicsHandle);
	}
	Super::EndPlay(EndPlayReason);
}

void AFleetEnvironment::BindControls()
{
	APlayerController* Controller = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (Controller && !FParse::Param(FCommandLine::Get(), TEXT("ShipShots")))
	{
		Controller->bShowMouseCursor = true;
		Controller->bEnableClickEvents = true;
		Controller->bEnableMouseOverEvents = true;
		FInputModeGameAndUI InputMode;
		InputMode.SetHideCursorDuringCapture(false);
		InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		Controller->SetInputMode(InputMode);
	}
	if (!Controller)
	{
		return;
	}
	EnableInput(Controller);
	if (!InputComponent)
	{
		return;
	}
	InputComponent->BindKey(EKeys::One, IE_Pressed, this, &AFleetEnvironment::Time1);
	InputComponent->BindKey(EKeys::Five, IE_Pressed, this, &AFleetEnvironment::Time5);
	InputComponent->BindKey(EKeys::Zero, IE_Pressed, this, &AFleetEnvironment::Time10);
	InputComponent->BindKey(EKeys::Two, IE_Pressed, this, &AFleetEnvironment::Time20);
	InputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this, &AFleetEnvironment::TogglePause);
	InputComponent->BindKey(EKeys::Enter, IE_Pressed, this, &AFleetEnvironment::StartSimulation);
	InputComponent->BindKey(EKeys::BackSpace, IE_Pressed, this, &AFleetEnvironment::ResetSimulation);
	InputComponent->BindKey(EKeys::Z, IE_Pressed, this, &AFleetEnvironment::Preset0);
	InputComponent->BindKey(EKeys::X, IE_Pressed, this, &AFleetEnvironment::Preset1);
	InputComponent->BindKey(EKeys::C, IE_Pressed, this, &AFleetEnvironment::Preset2);
	InputComponent->BindKey(EKeys::V, IE_Pressed, this, &AFleetEnvironment::Preset3);
	InputComponent->BindKey(EKeys::Up, IE_Pressed, this, &AFleetEnvironment::WindFaster);
	InputComponent->BindKey(EKeys::Down, IE_Pressed, this, &AFleetEnvironment::WindSlower);
	InputComponent->BindKey(EKeys::Left, IE_Pressed, this, &AFleetEnvironment::WindLeft);
	InputComponent->BindKey(EKeys::Right, IE_Pressed, this, &AFleetEnvironment::WindRight);
	InputComponent->BindKey(EKeys::I, IE_Pressed, this, &AFleetEnvironment::CurrentFaster);
	InputComponent->BindKey(EKeys::K, IE_Pressed, this, &AFleetEnvironment::CurrentSlower);
	InputComponent->BindKey(EKeys::J, IE_Pressed, this, &AFleetEnvironment::CurrentLeft);
	InputComponent->BindKey(EKeys::L, IE_Pressed, this, &AFleetEnvironment::CurrentRight);
	InputComponent->BindKey(EKeys::U, IE_Pressed, this, &AFleetEnvironment::WavesHigher);
	InputComponent->BindKey(EKeys::O, IE_Pressed, this, &AFleetEnvironment::WavesLower);
	InputComponent->BindKey(EKeys::Y, IE_Pressed, this, &AFleetEnvironment::WavesLeft);
	InputComponent->BindKey(EKeys::H, IE_Pressed, this, &AFleetEnvironment::WavesRight);
	InputComponent->BindKey(EKeys::F5, IE_Pressed, this, &AFleetEnvironment::VisualCalm);
	InputComponent->BindKey(EKeys::F6, IE_Pressed, this, &AFleetEnvironment::VisualModerate);
	InputComponent->BindKey(EKeys::F7, IE_Pressed, this, &AFleetEnvironment::VisualRough);
	InputComponent->BindKey(EKeys::T, IE_Pressed, this, &AFleetEnvironment::HourLater);
	InputComponent->BindKey(EKeys::G, IE_Pressed, this, &AFleetEnvironment::HourEarlier);
	InputComponent->BindKey(EKeys::N, IE_Pressed, this, &AFleetEnvironment::ToggleDayNightCycle);
}

void AFleetEnvironment::LaunchPhysics()
{
	ISocketSubsystem* Sockets = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	if (!Sockets)
	{
		return;
	}
	PhysicsSocket = Sockets->CreateSocket(NAME_DGram, TEXT("MmgBridge"), true);
	if (!PhysicsSocket)
	{
		return;
	}
	PhysicsSocket->SetNonBlocking(true);
	PhysicsAddress = Sockets->CreateInternetAddr();
	bool bValid = false;
	PhysicsAddress->SetIp(TEXT("127.0.0.1"), bValid);
	PhysicsAddress->SetPort(9001);

	const FString Script = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir() / TEXT("scripts/mmg_physics.py"));
	const FString LogFile = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir() / TEXT("logs/mmg_physics.log"));
	const FString Args = FString::Printf(TEXT("-c \"exec python3 '%s' >> '%s' 2>&1\""), *Script, *LogFile);
	PhysicsHandle = FPlatformProcess::CreateProc(TEXT("/bin/bash"), *Args, false, true, true, &PhysicsPid, 0, nullptr, nullptr);
	FPlatformProcess::Sleep(0.25f);
	UE_LOG(LogTemp, Display, TEXT("MMG physics process %u, script %s"), PhysicsPid, *Script);
}

void AFleetEnvironment::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!InputComponent)
	{
		BindControls();
	}
	const double Now = FPlatformTime::Seconds();
	const float RealDt = LastRealSeconds > 0.0 ? float(Now - LastRealSeconds) : 0.f;
	LastRealSeconds = Now;

	if (bDayNight && !bPaused)
	{
		Hour = FMath::Fmod(Hour + RealDt * 0.25f + 24.f, 24.f);
		ApplySun();
	}

	if (bEnvDemo && !bPaused)
	{
		DemoAccum += RealDt;
		if (DemoAccum >= 5.f)
		{
			DemoAccum = 0.f;
			PresetIndex = (PresetIndex + 1) % UE_ARRAY_COUNT(Presets);
			ApplyPreset(PresetIndex);
			ResetSimulation();
		}
	}

	if (!bOceanStyled && OceanStyleAttempts < 180)
	{
		StyleOceanSurface();
	}

	if (bControlDemo)
	{
		RunControlDemo(RealDt);
	}

	if (!bPaused)
	{
		const float Step = FMath::Min(DeltaSeconds, 0.25f);
		SimTime += Step;
		ExchangePhysics(Step);
		if (bVoyageCompare)
		{
			TrackVoyage(Step);
		}
	}
	UpdateVisualSea();
}

namespace
{
	struct FVoyageTrack
	{
		TWeakObjectPtr<AFleetShip> Ship;
		FVector Last = FVector::ZeroVector;
		bool bHasLast = false;
		bool bFinished = false;
		float PathCm = 0.f;
		float FuelT = 0.f;
		float OffsetSumM = 0.f;
		float OffsetMaxM = 0.f;
		int32 Samples = 0;
		float FinishSim = 0.f;
	};

	TArray<FVoyageTrack> VoyageTracks;
	int32 VoyagePhase = 0;
	float VoyageSim = 0.f;
	bool bVoyageOpen = true;

	float DistanceToRoute(const FVector& Origin, const TArray<FVector>& Waypoints, const FVector& Point)
	{
		TArray<FVector> Points;
		Points.Add(Origin);
		Points.Append(Waypoints);
		float Best = 1.0e12f;
		for (int32 Index = 0; Index + 1 < Points.Num(); ++Index)
		{
			const FVector A = Points[Index];
			const FVector B = Points[Index + 1];
			const float Abx = B.X - A.X;
			const float Aby = B.Y - A.Y;
			const float Den = Abx * Abx + Aby * Aby;
			float Along = 0.f;
			if (Den > 1.f)
			{
				Along = FMath::Clamp(((Point.X - A.X) * Abx + (Point.Y - A.Y) * Aby) / Den, 0.f, 1.f);
			}
			const FVector Closest(A.X + Abx * Along, A.Y + Aby * Along, 0.f);
			Best = FMath::Min(Best, FVector::Dist2D(Point, Closest));
		}
		return Best;
	}

	float PlannedCm(const AFleetShip& Ship)
	{
		FVector Previous = Ship.GetRouteOrigin();
		float Total = 0.f;
		for (const FVector& Waypoint : Ship.GetWaypoints())
		{
			Total += FVector::Dist2D(Previous, Waypoint);
			Previous = Waypoint;
		}
		return Total;
	}
}

void AFleetEnvironment::TrackVoyage(float DeltaSeconds)
{
	if (!bVoyageOpen || DeltaSeconds <= KINDA_SMALL_NUMBER)
	{
		return;
	}

	VoyageSim += DeltaSeconds;
	bool bAny = false;
	bool bAllFinished = true;
	for (TActorIterator<AFleetShip> It(GetWorld()); It; ++It)
	{
		bAny = true;
		FVoyageTrack* Track = nullptr;
		for (FVoyageTrack& Existing : VoyageTracks)
		{
			if (Existing.Ship.Get() == *It)
			{
				Track = &Existing;
				break;
			}
		}
		if (!Track)
		{
			FVoyageTrack Created;
			Created.Ship = *It;
			VoyageTracks.Add(Created);
			Track = &VoyageTracks.Last();
		}
		if (Track->bFinished)
		{
			continue;
		}
		bAllFinished = false;
		const FVector Location = It->GetActorLocation();
		if (Track->bHasLast)
		{
			Track->PathCm += FVector::Dist2D(Track->Last, Location);
			Track->FuelT += It->GetFuelTonnesPerHour() * DeltaSeconds / 3600.f;
			const float OffsetM = DistanceToRoute(It->GetRouteOrigin(), It->GetWaypoints(), Location) / 100.f;
			Track->OffsetSumM += OffsetM;
			Track->OffsetMaxM = FMath::Max(Track->OffsetMaxM, OffsetM);
			Track->Samples += 1;
		}
		Track->Last = Location;
		Track->bHasLast = true;
		if (Track->Samples > 20 && It->GetDistanceRemainingMeters() < 80.f)
		{
			Track->bFinished = true;
			Track->FinishSim = VoyageSim;
		}
	}
	if (!bAny)
	{
		return;
	}

	bAllFinished = VoyageTracks.Num() > 0;
	for (const FVoyageTrack& Track : VoyageTracks)
	{
		if (!Track.bFinished)
		{
			bAllFinished = false;
		}
	}
	const bool bTimedOut = VoyageSim > 600.f;
	if (!bAllFinished && !bTimedOut)
	{
		return;
	}

	for (const FVoyageTrack& Track : VoyageTracks)
	{
		const AFleetShip* Ship = Track.Ship.Get();
		if (!Ship)
		{
			continue;
		}
		const float PlannedM = PlannedCm(*Ship) / 100.f;
		const float PathM = Track.PathCm / 100.f;
		const float Elapsed = Track.bFinished ? Track.FinishSim : VoyageSim;
		const float MeanOffset = Track.Samples > 0 ? Track.OffsetSumM / Track.Samples : 0.f;
		const float MeanKn = Elapsed > 1.f ? (PathM / Elapsed) * 1.943844f : 0.f;
		UE_LOG(LogTemp, Display, TEXT("VOYAGE %s | %s | sim %.1f s | path %.0f m | planned %.0f m | mean offset %.1f m | max offset %.1f m | fuel %.3f t | mean %.1f kn | %s"),
			*Ship->GetShipName(), *PresetName, Elapsed, PathM, PlannedM, MeanOffset, Track.OffsetMaxM, Track.FuelT, MeanKn,
			Track.bFinished ? TEXT("arrived") : TEXT("timed out"));
	}

	if (VoyagePhase == 0)
	{
		VoyagePhase = 1;
		VoyageSim = 0.f;
		VoyageTracks.Reset();
		ApplyPreset(3);
		ResetSimulation();
		return;
	}

	bVoyageOpen = false;
	UE_LOG(LogTemp, Display, TEXT("VOYAGE COMPARE COMPLETE"));
}

void AFleetEnvironment::SetTimeScale(float Scale)
{
	TimeScale = FMath::Clamp(Scale, 0.f, 30.f);
	ResumeScale = FMath::Max(TimeScale, 1.f);
	bPaused = false;
	if (AWorldSettings* Settings = GetWorld()->GetWorldSettings())
	{
		Settings->SetTimeDilation(TimeScale);
	}
	UE_LOG(LogTemp, Display, TEXT("ENV time scale %.0fx"), TimeScale);
}

void AFleetEnvironment::TogglePause()
{
	if (bPaused)
	{
		StartSimulation();
		return;
	}
	bPaused = true;
	ResumeScale = FMath::Max(TimeScale, 1.f);
	if (AWorldSettings* Settings = GetWorld()->GetWorldSettings())
	{
		Settings->SetTimeDilation(0.f);
	}
	UE_LOG(LogTemp, Display, TEXT("ENV paused"));
}

void AFleetEnvironment::StartSimulation()
{
	bPaused = false;
	if (TimeScale < 1.f)
	{
		TimeScale = ResumeScale;
	}
	if (AWorldSettings* Settings = GetWorld()->GetWorldSettings())
	{
		Settings->SetTimeDilation(TimeScale);
	}
	UE_LOG(LogTemp, Display, TEXT("ENV running %.0fx"), TimeScale);
}

void AFleetEnvironment::ResetSimulation()
{
	for (TActorIterator<AFleetShip> It(GetWorld()); It; ++It)
	{
		It->ResetVoyage();
	}
	UE_LOG(LogTemp, Display, TEXT("ENV reset on %s"), *PresetName);
}

void AFleetEnvironment::ApplyPreset(int32 Index)
{
	Index = FMath::Clamp(Index, 0, UE_ARRAY_COUNT(Presets) - 1);
	const FSeaPreset& Preset = Presets[Index];
	PresetIndex = Index;
	PresetName = Preset.Name;
	Month = Preset.Month;
	Hour = Preset.Hour;
	WindMs = Preset.WindMs;
	WindDeg = Preset.WindDeg;
	CurrentMs = Preset.CurrentMs;
	CurrentDeg = Preset.CurrentDeg;
	WaveM = Preset.WaveM;
	WaveDeg = Preset.WaveDeg;
	SunLux = Preset.Lux;
	ExposureBias = Preset.Exposure;
	SunColor = Preset.SunColor;
	bDayNight = false;
	ApplySeaToWorld();
	UE_LOG(LogTemp, Display, TEXT("ENV PRESET %s wind %.1f m/s at %.0f, current %.2f m/s at %.0f, waves %.1f m at %.0f, hour %.1f"),
		*PresetName, WindMs, WindDeg, CurrentMs, CurrentDeg, WaveM, WaveDeg, Hour);
}

void AFleetEnvironment::MarkCustom()
{
	PresetName = TEXT("custom");
	ApplySeaToWorld();
}

void AFleetEnvironment::NudgeWindSpeed(float DeltaMs)
{
	WindMs = FMath::Clamp(WindMs + DeltaMs, 0.f, 35.f);
	MarkCustom();
}

void AFleetEnvironment::NudgeWindDirection(float DeltaDeg)
{
	WindDeg = FMath::Fmod(WindDeg + DeltaDeg + 360.f, 360.f);
	MarkCustom();
}

void AFleetEnvironment::NudgeCurrentSpeed(float DeltaMs)
{
	CurrentMs = FMath::Clamp(CurrentMs + DeltaMs, 0.f, 3.f);
	MarkCustom();
}

void AFleetEnvironment::NudgeCurrentDirection(float DeltaDeg)
{
	CurrentDeg = FMath::Fmod(CurrentDeg + DeltaDeg + 360.f, 360.f);
	MarkCustom();
}

void AFleetEnvironment::NudgeWaveHeight(float DeltaM)
{
	WaveM = FMath::Clamp(WaveM + DeltaM, 0.f, 6.f);
	MarkCustom();
}

void AFleetEnvironment::NudgeWaveDirection(float DeltaDeg)
{
	WaveDeg = FMath::Fmod(WaveDeg + DeltaDeg + 360.f, 360.f);
	MarkCustom();
}

void AFleetEnvironment::NudgeHour(float DeltaHours)
{
	Hour = FMath::Fmod(Hour + DeltaHours + 24.f, 24.f);
	bDayNight = false;
	PresetName = TEXT("custom");
	ApplySun();
}

void AFleetEnvironment::ToggleDayNightCycle()
{
	bDayNight = !bDayNight;
	UE_LOG(LogTemp, Display, TEXT("ENV day/night cycle %s"), bDayNight ? TEXT("on") : TEXT("off"));
}

namespace
{
	struct FVisualSea
	{
		const TCHAR* Name;
		int32 NumWaves;
		float MinWavelength;
		float MaxWavelength;
		float SpreadDeg;
		float SmallSteepness;
		float LargeSteepness;
		float Randomness;
		float Roughness;
		float Foam;
		float FoamBoost;
		float MinAmplitudeCm;
		float MaxAmplitudeCm;
	};

	const FVisualSea VisualSeas[] = {
		{ TEXT("calm visual"), 8, 2200.f, 16000.f, 28.f, 0.22f, 0.12f, 0.12f, 0.11f, 0.28f, 0.5f, 8.f, 28.f },
		{ TEXT("moderate visual"), 12, 900.f, 11000.f, 58.f, 0.48f, 0.26f, 0.28f, 0.05f, 0.85f, 1.2f, 14.f, 72.f },
		{ TEXT("rough visual"), 14, 1100.f, 15000.f, 80.f, 0.62f, 0.34f, 0.36f, 0.04f, 1.25f, 1.55f, 22.f, 130.f }
	};
}

void AFleetEnvironment::SetVisualSea(int32 Index)
{
	VisualSea = FMath::Clamp(Index, 0, UE_ARRAY_COUNT(VisualSeas) - 1);
	VisualSeaName = VisualSeas[VisualSea].Name;
	UE_LOG(LogTemp, Display, TEXT("VISUAL SEA %s. Physics wave height stays %.2f m"), *VisualSeaName, WaveM);
	ApplySeaToWorld();
}

void AFleetEnvironment::ApplySeaToWorld()
{
	VisualSea = FMath::Clamp(VisualSea, 0, UE_ARRAY_COUNT(VisualSeas) - 1);
	const FVisualSea& Sea = VisualSeas[VisualSea];
	VisualSeaName = Sea.Name;
	if (UWorld* World = GetWorld())
	{
		TActorIterator<AWaterBodyOcean> OceanIt(World);
		AWaterBodyOcean* Ocean = OceanIt ? *OceanIt : nullptr;
		if (Ocean)
		{
			if (UWaterBodyComponent* OceanBody = Ocean->GetWaterBodyComponent())
			{
				OceanBody->TargetWaveMaskDepth = 600.f;
			}
			UGerstnerWaterWaves* Waves = Cast<UGerstnerWaterWaves>(Ocean->GetWaterWaves());
			UGerstnerWaterWaveGeneratorSimple* Generator = Waves ? Cast<UGerstnerWaterWaveGeneratorSimple>(Waves->GerstnerWaveGenerator) : nullptr;
			if (Waves && Generator)
			{
				Generator->NumWaves = Sea.NumWaves;
				Generator->MinWavelength = Sea.MinWavelength;
				Generator->MaxWavelength = Sea.MaxWavelength;
				Generator->WavelengthFalloff = 1.55f;
				Generator->AmplitudeFalloff = 1.65f;
				Generator->MinAmplitude = Sea.MinAmplitudeCm;
				Generator->MaxAmplitude = Sea.MaxAmplitudeCm;
				Generator->WindAngleDeg = WaveDeg;
				Generator->DirectionAngularSpreadDeg = Sea.SpreadDeg;
				Generator->SmallWaveSteepness = Sea.SmallSteepness;
				Generator->LargeWaveSteepness = Sea.LargeSteepness;
				Generator->SteepnessFalloff = 0.9f;
				Generator->Randomness = Sea.Randomness;
				Waves->RecomputeWaves(false);
				Ocean->SetWaterWaves(Waves);
				UE_LOG(LogTemp, Display, TEXT("VISUAL WAVES %s, %d components, amplitude %.0f-%.0f cm, summed crest %.0f cm. Physics wave height stays %.2f m"),
					Sea.Name, Generator->NumWaves, Generator->MinAmplitude, Generator->MaxAmplitude, Waves->GetMaxWaveHeight(), WaveM);
			}
		}
	}
	ApplySun();
	StyleOceanSurface();
}

void AFleetEnvironment::StyleOceanSurface()
{
	if (bOceanStyled)
	{
		// Material parameters still follow the visual sea. The physics wave height does not.
	}
	else if (OceanStyleAttempts >= 180)
	{
		return;
	}
	if (!bOceanStyled)
	{
		++OceanStyleAttempts;
	}
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	TActorIterator<AWaterBodyOcean> OceanIt(World);
	AWaterBodyOcean* Ocean = OceanIt ? *OceanIt : nullptr;
	UWaterBodyComponent* Body = Ocean ? Ocean->GetWaterBodyComponent() : nullptr;
	if (Body && !Body->GetWaterMaterial())
	{
		if (UMaterialInterface* OceanMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Water/Materials/WaterSurface/Water_Material_Ocean.Water_Material_Ocean")))
		{
			Ocean->SetWaterMaterial(OceanMaterial);
		}
	}
	UMaterialInstanceDynamic* Water = Ocean ? Ocean->GetWaterMaterialInstance() : nullptr;
	if (!Water)
	{
		if (OceanStyleAttempts == 180)
		{
			UE_LOG(LogTemp, Warning, TEXT("Ocean material instance was not ready"));
		}
		return;
	}
	Water->SetVectorParameterValue(TEXT("Water Albedo"), FLinearColor(0.007f, 0.028f, 0.040f));
	Water->SetVectorParameterValue(TEXT("ScatteringCoefficients"), FLinearColor(0.11f, 0.30f, 0.46f));
	Water->SetVectorParameterValue(TEXT("AbsorptionCoefficients"), FLinearColor(42.f, 14.f, 4.5f));
	Water->SetVectorParameterValue(TEXT("ColorScaleBehindWater"), FLinearColor(0.011f, 0.058f, 0.082f));
	if (Body)
	{
		if (UMaterialInstanceDynamic* Lod = Body->GetWaterMaterialInstance())
		{
			Lod->SetVectorParameterValue(TEXT("Water Albedo"), FLinearColor(0.007f, 0.028f, 0.040f));
			Lod->SetVectorParameterValue(TEXT("ScatteringCoefficients"), FLinearColor(0.11f, 0.30f, 0.46f));
			Lod->SetVectorParameterValue(TEXT("AbsorptionCoefficients"), FLinearColor(42.f, 14.f, 4.5f));
			Lod->SetVectorParameterValue(TEXT("ColorScaleBehindWater"), FLinearColor(0.011f, 0.058f, 0.082f));
		}
		if (UMaterialInstanceDynamic* StaticLod = Body->GetWaterStaticMeshMaterialInstance())
		{
			StaticLod->SetVectorParameterValue(TEXT("Water Albedo"), FLinearColor(0.007f, 0.028f, 0.040f));
			StaticLod->SetVectorParameterValue(TEXT("ScatteringCoefficients"), FLinearColor(0.11f, 0.30f, 0.46f));
			StaticLod->SetVectorParameterValue(TEXT("ColorScaleBehindWater"), FLinearColor(0.011f, 0.058f, 0.082f));
		}
	}
	const int32 SeaIndex = FMath::Clamp(VisualSea, 0, UE_ARRAY_COUNT(VisualSeas) - 1);
	const FVisualSea& Sea = VisualSeas[SeaIndex];
	const float FoamScale = FMath::Clamp(0.55f + WaveM * 0.18f, 0.45f, 1.7f);
	const float WaterRoughness = FMath::Clamp(Sea.Roughness + 0.12f, 0.f, 1.f);
	Water->SetScalarParameterValue(TEXT("Water Roughness"), WaterRoughness);
	Water->SetScalarParameterValue(TEXT("Foam Opacity"), Sea.Foam * FoamScale);
	Water->SetScalarParameterValue(TEXT("Foam Boost"), Sea.FoamBoost);
	if (Body)
	{
		if (UMaterialInstanceDynamic* Lod = Body->GetWaterMaterialInstance())
		{
			Lod->SetScalarParameterValue(TEXT("Water Roughness"), WaterRoughness);
			Lod->SetScalarParameterValue(TEXT("Foam Opacity"), Sea.Foam * FoamScale);
			Lod->SetScalarParameterValue(TEXT("Foam Boost"), Sea.FoamBoost);
		}
		if (UMaterialInstanceDynamic* StaticLod = Body->GetWaterStaticMeshMaterialInstance())
		{
			StaticLod->SetScalarParameterValue(TEXT("Water Roughness"), WaterRoughness);
		}
	}
	if (!bOceanStyled)
	{
		bOceanStyled = true;
		UE_LOG(LogTemp, Display, TEXT("Ocean surface styled, attempt %d, %s, physics waves %.2f m"), OceanStyleAttempts, *VisualSeaName, WaveM);
	}
}

void AFleetEnvironment::ApplySun()
{
	const int32 WholeHour = FMath::Clamp(FMath::FloorToInt(Hour), 0, 23);
	const int32 Minute = FMath::Clamp(FMath::FloorToInt((Hour - WholeHour) * 60.f), 0, 59);
	FSunPositionData Sun;
	USunPositionFunctionLibrary::GetSunPosition(40.f, -40.f, 0.f, false, 2026, Month, 21, WholeHour, Minute, 0, Sun);
	float Elevation = Sun.CorrectedElevation;
	if (Elevation > 90.f)
	{
		Elevation -= 180.f;
	}
	const FRotator SunRotation(Elevation - 90.f, Sun.Azimuth, 0.f);
	if (UWorld* World = GetWorld())
	{
		for (TActorIterator<ADirectionalLight> It(World); It; ++It)
		{
			It->SetActorRotation(SunRotation);
			if (ULightComponent* Light = It->GetLightComponent())
			{
				Light->SetIntensity(SunLux);
				Light->SetLightColor(SunColor);
			}
		}
		for (TActorIterator<ASkyLight> It(World); It; ++It)
		{
			if (USkyLightComponent* Sky = It->GetLightComponent())
			{
				Sky->SetIntensity(FMath::Max(0.15f, SunLux / 12.f));
			}
		}
	}
	if (GEngine)
	{
		GEngine->Exec(GetWorld(), *FString::Printf(TEXT("r.EyeAdaptation.ExposureCompensation %f"), ExposureBias));
	}
}

void AFleetEnvironment::ExchangePhysics(float DeltaSeconds)
{
	if (!PhysicsSocket || !PhysicsAddress)
	{
		return;
	}

	TArray<AFleetShip*> Ships;
	for (TActorIterator<AFleetShip> It(GetWorld()); It; ++It)
	{
		It->UpdateAutopilot(DeltaSeconds);
		Ships.Add(*It);
	}
	if (Ships.Num() == 0)
	{
		return;
	}

	TArray<uint8> Packet;
	Packet.Reserve(48 + Ships.Num() * 80);
	const uint8 Magic[4] = { 'M', 'M', 'G', '1' };
	AppendBytes(Packet, Magic, 4);
	const uint32 Seq = PacketSeq++;
	const uint32 Count = Ships.Num();
	Append(Packet, Seq);
	Append(Packet, Count);
	Append(Packet, DeltaSeconds);
	Append(Packet, SimTime);
	Append(Packet, WindMs * 100.f);
	Append(Packet, WindDeg);
	Append(Packet, CurrentMs * 100.f);
	Append(Packet, CurrentDeg);
	Append(Packet, WaveM * 100.f);
	Append(Packet, WaveDeg);
	for (int32 Index = 0; Index < Ships.Num(); ++Index)
	{
		const AFleetShip* Ship = Ships[Index];
		const FVector Location = Ship->GetActorLocation();
		Append(Packet, static_cast<uint32>(Index));
		Append(Packet, static_cast<float>(Location.X));
		Append(Packet, static_cast<float>(Location.Y));
		Append(Packet, Ship->GetHeadingDegrees());
		Append(Packet, Ship->GetSurgeCms());
		Append(Packet, Ship->GetSwayCms());
		Append(Packet, Ship->GetYawRate());
		Append(Packet, Ship->GetRudderDegrees());
		Append(Packet, Ship->GetDesiredSpeedMs());
		Append(Packet, Ship->GetMassKg());
		Append(Packet, Ship->GetLengthCm());
		Append(Packet, Ship->GetBeamCm());
		Append(Packet, Ship->GetDraftCm());
		Append(Packet, Ship->GetFreeboardCm());
		Append(Packet, Ship->GetEnginePowerW());
		Append(Packet, Ship->GetWettedAreaM2());
		Append(Packet, Ship->GetFrontalAreaM2());
		Append(Packet, Ship->GetLateralAreaM2());
		Append(Packet, Ship->GetServiceCms());
	}

	int32 Sent = 0;
	PhysicsSocket->SendTo(Packet.GetData(), Packet.Num(), Sent, *PhysicsAddress);
	const bool bReadable = PhysicsSocket->Wait(ESocketWaitConditions::WaitForRead, FTimespan::FromMilliseconds(15));
	uint8 Reply[2048];
	uint8 Matched[2048];
	int32 MatchedRead = 0;
	bool bMatched = false;
	if (bReadable)
	{
		TSharedRef<FInternetAddr> From = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->CreateInternetAddr();
		int32 Read = 0;
		while (PhysicsSocket->RecvFrom(Reply, sizeof(Reply), Read, *From))
		{
			if (Read < 12 || FMemory::Memcmp(Reply, "RMG1", 4) != 0)
			{
				continue;
			}
			uint32 ReplySeq = 0;
			FMemory::Memcpy(&ReplySeq, Reply + 4, 4);
			if (ReplySeq == Seq)
			{
				FMemory::Memcpy(Matched, Reply, Read);
				MatchedRead = Read;
				bMatched = true;
			}
		}
	}
	if (!bMatched)
	{
		++MissedReplies;
		if (MissedReplies == 45 && !bLoggedDisconnect)
		{
			UE_LOG(LogTemp, Warning, TEXT("MMG physics has not answered yet"));
			bLoggedDisconnect = true;
			bPhysicsConnected = false;
		}
		return;
	}

	if (!bPhysicsConnected)
	{
		UE_LOG(LogTemp, Display, TEXT("MMG physics connected"));
	}
	bPhysicsConnected = true;
	bLoggedDisconnect = false;
	MissedReplies = 0;
	bCommandRejected = false;
	uint32 ReplyCount = 0;
	FMemory::Memcpy(&ReplyCount, Matched + 8, 4);
	const int32 Stride = 4 + 9 * 4;
	const int32 AckOffset = 12 + static_cast<int32>(FMath::Min(ReplyCount, 8u)) * Stride;
	if (AckOffset + 4 <= MatchedRead && FMemory::Memcmp(Matched + AckOffset, "REJ1", 4) == 0)
	{
		bCommandRejected = true;
		bPhysicsAck = false;
		UE_LOG(LogTemp, Warning, TEXT("MMG rejected a non-finite environment packet"));
		return;
	}
	if (AckOffset + 28 <= MatchedRead && FMemory::Memcmp(Matched + AckOffset, "ACK1", 4) == 0)
	{
		float Applied[6];
		FMemory::Memcpy(Applied, Matched + AckOffset + 4, sizeof(Applied));
		const bool bChanged = !bPhysicsAck
			|| !FMath::IsNearlyEqual(AppliedWindMs, Applied[0] / 100.f, 0.01f)
			|| !FMath::IsNearlyEqual(AppliedCurrentMs, Applied[2] / 100.f, 0.01f)
			|| !FMath::IsNearlyEqual(AppliedWaveM, Applied[4] / 100.f, 0.01f)
			|| !FMath::IsNearlyEqual(AppliedWindDeg, Applied[1], 0.5f)
			|| !FMath::IsNearlyEqual(AppliedCurrentDeg, Applied[3], 0.5f)
			|| !FMath::IsNearlyEqual(AppliedWaveDeg, Applied[5], 0.5f);
		AppliedWindMs = Applied[0] / 100.f;
		AppliedWindDeg = Applied[1];
		AppliedCurrentMs = Applied[2] / 100.f;
		AppliedCurrentDeg = Applied[3];
		AppliedWaveM = Applied[4] / 100.f;
		AppliedWaveDeg = Applied[5];
		bPhysicsAck = true;
		if (bChanged)
		{
			UE_LOG(LogTemp, Display, TEXT("MMG APPLIED wind %.2f m/s at %.0f, current %.2f m/s at %.0f, waves %.2f m at %.0f, sim %.1f s"),
				AppliedWindMs, AppliedWindDeg, AppliedCurrentMs, AppliedCurrentDeg, AppliedWaveM, AppliedWaveDeg, SimTime);
		}
	}
	for (uint32 Index = 0; Index < ReplyCount && Index < static_cast<uint32>(Ships.Num()); ++Index)
	{
		const int32 Offset = 12 + static_cast<int32>(Index) * Stride;
		if (Offset + Stride > MatchedRead)
		{
			break;
		}
		float Values[9];
		FMemory::Memcpy(Values, Matched + Offset + 4, sizeof(Values));
		Ships[Index]->ApplyMotion(DeltaSeconds, Values[0], Values[1], Values[2], Values[3], Values[4], Values[5], Values[6], Values[7]);
	}
}

void AFleetEnvironment::LogControlShip(const TCHAR* Label) const
{
	for (TActorIterator<AFleetShip> It(GetWorld()); It; ++It)
	{
		if (It->GetShipType() != EFleetShipType::Container)
		{
			continue;
		}
		const FVector Place = It->GetActorLocation();
		UE_LOG(LogTemp, Display, TEXT("CONTROL SHIP %s kn %.1f heading %.1f pos %.0f %.0f m heave %+.2f m leeway %+.1f deg sim %.2f s"),
			Label, It->GetSpeedKnots(), It->GetHeadingDegrees(), Place.X / 100.f, Place.Y / 100.f,
			It->GetHeaveMeters(), It->GetLeewayDegrees(), SimTime);
	}
}

void AFleetEnvironment::RunControlDemo(float RealDt)
{
	ControlDemoTime += RealDt;
	if (ControlDemoStage == 0 && ControlDemoTime > 8.f)
	{
		LogControlShip(TEXT("summer"));
		ApplyPreset(3);
		UE_LOG(LogTemp, Display, TEXT("CONTROL weather winter storm"));
		ControlDemoStage = 1;
	}
	else if (ControlDemoStage == 1 && ControlDemoTime > 22.f)
	{
		LogControlShip(TEXT("winter"));
		ApplyPreset(0);
		UE_LOG(LogTemp, Display, TEXT("CONTROL weather back to summer calm"));
		ControlDemoStage = 2;
	}
	else if (ControlDemoStage == 2 && ControlDemoTime > 26.f)
	{
		NudgeCurrentSpeed(1.75f);
		NudgeCurrentDirection(50.f);
		UE_LOG(LogTemp, Display, TEXT("CONTROL current 2.00 m/s at 90"));
		ControlDemoStage = 3;
	}
	else if (ControlDemoStage == 3 && ControlDemoTime > 42.f)
	{
		LogControlShip(TEXT("current"));
		NudgeWaveHeight(3.6f);
		UE_LOG(LogTemp, Display, TEXT("CONTROL waves 4.00 m"));
		ControlDemoStage = 4;
	}
	else if (ControlDemoStage == 4 && ControlDemoTime > 58.f)
	{
		LogControlShip(TEXT("waves"));
		TogglePause();
		UE_LOG(LogTemp, Display, TEXT("CONTROL pause sim %.2f s"), SimTime);
		ControlDemoStage = 5;
	}
	else if (ControlDemoStage == 5 && ControlDemoTime > 70.f)
	{
		LogControlShip(TEXT("paused"));
		UE_LOG(LogTemp, Display, TEXT("CONTROL paused sim still %.2f s"), SimTime);
		StartSimulation();
		SetTimeScale(5.f);
		ControlDemoStage = 6;
	}
	else if (ControlDemoStage == 6 && ControlDemoTime > 82.f)
	{
		LogControlShip(TEXT("fast"));
		UE_LOG(LogTemp, Display, TEXT("CONTROL DEMO COMPLETE sim %.2f s"), SimTime);
		ControlDemoStage = 7;
	}
	else if (ControlDemoStage == 7 && ControlDemoTime > 90.f)
	{
		FPlatformMisc::RequestExit(false);
		ControlDemoStage = 8;
	}
}

void AFleetEnvironment::BuildVisualSea()
{
	const int32 Resolution = FMath::Clamp(VisualSeaResolution, 24, 140);
	VisualSeaResolution = Resolution;
	const int32 Count = Resolution + 1;
	VisualSeaXY.SetNum(Count * Count);
	VisualSeaTriangles.Reset();
	VisualSeaTriangles.Reserve(Resolution * Resolution * 6);
	const float RadiusCm = 220000.f;
	for (int32 Y = 0; Y < Count; ++Y)
	{
		for (int32 X = 0; X < Count; ++X)
		{
			const float U = (static_cast<float>(X) / Resolution) * 2.f - 1.f;
			const float V = (static_cast<float>(Y) / Resolution) * 2.f - 1.f;
			FVector2D Point(U * RadiusCm, V * RadiusCm);
			const float Radial = Point.Size();
			if (Radial > RadiusCm)
			{
				Point *= RadiusCm / Radial;
			}
			VisualSeaXY[Y * Count + X] = Point;
		}
	}
	for (int32 Y = 0; Y < Resolution; ++Y)
	{
		for (int32 X = 0; X < Resolution; ++X)
		{
			const int32 Index = Y * Count + X;
			const float CenterRadius = (VisualSeaXY[Index] + VisualSeaXY[Index + Count + 1]).Size() * 0.5f;
			if (CenterRadius > RadiusCm)
			{
				continue;
			}
			VisualSeaTriangles.Add(Index);
			VisualSeaTriangles.Add(Index + 1);
			VisualSeaTriangles.Add(Index + Count);
			VisualSeaTriangles.Add(Index + 1);
			VisualSeaTriangles.Add(Index + Count + 1);
			VisualSeaTriangles.Add(Index + Count);
		}
	}

	VisualSeaMesh = NewObject<UProceduralMeshComponent>(this, TEXT("VisualSea"));
	VisualSeaMesh->SetupAttachment(GetRootComponent());
	VisualSeaMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	VisualSeaMesh->SetCastShadow(false);
	VisualSeaMesh->SetCanEverAffectNavigation(false);
	VisualSeaMesh->RegisterComponent();
	SetRootComponent(VisualSeaMesh);
	if (UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial")))
	{
		UMaterialInstanceDynamic* SeaMaterial = UMaterialInstanceDynamic::Create(Base, this);
		SeaMaterial->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.014f, 0.062f, 0.098f));
		SeaMaterial->SetScalarParameterValue(TEXT("Roughness"), 0.58f);
		VisualSeaMesh->SetMaterial(0, SeaMaterial);
	}

	if (UWorld* World = GetWorld())
	{
		TActorIterator<AWaterZone> ZoneIt(World);
		if (AWaterZone* Zone = ZoneIt ? *ZoneIt : nullptr)
		{
			if (UWaterMeshComponent* WaterMesh = Zone->GetWaterMeshComponent())
			{
				WaterMesh->SetVisibility(false);
				WaterMesh->SetHiddenInGame(true);
			}
		}
		TActorIterator<AWaterBodyOcean> OceanIt(World);
		if (AWaterBodyOcean* Ocean = OceanIt ? *OceanIt : nullptr)
		{
			Ocean->SetActorHiddenInGame(true);
		}
	}

	bVisualSeaReady = true;
	if (GEngine)
	{
		GEngine->Exec(GetWorld(), TEXT("r.Water.WaterMesh.Enabled 0"));
	}
	UpdateVisualSea();
	UE_LOG(LogTemp, Display, TEXT("VISUAL SEA MESH %d x %d, circular extent, no square skirt. Physics wave height is unchanged."), Count, Count);
}

void AFleetEnvironment::UpdateVisualSea()
{
	if (!bVisualSeaReady || !VisualSeaMesh)
	{
		return;
	}
	const int32 SeaIndex = FMath::Clamp(VisualSea, 0, UE_ARRAY_COUNT(VisualSeas) - 1);
	const FVisualSea& Sea = VisualSeas[SeaIndex];
	const int32 Count = VisualSeaResolution + 1;
	const float Time = SimTime;
	FVector Center = FVector::ZeroVector;
	int32 ShipCount = 0;
	if (UWorld* World = GetWorld())
	{
		for (TActorIterator<AFleetShip> It(World); It; ++It)
		{
			Center += It->GetActorLocation();
			++ShipCount;
		}
	}
	if (ShipCount > 0)
	{
		Center /= ShipCount;
	}
	VisualSeaMesh->SetWorldLocation(FVector(Center.X, Center.Y, 0.f));

	VisualSeaVertices.SetNum(VisualSeaXY.Num());
	VisualSeaNormals.SetNum(VisualSeaXY.Num());
	VisualSeaUV.SetNum(VisualSeaXY.Num());
	VisualSeaColors.SetNum(VisualSeaXY.Num());
	struct FSeaWave
	{
		float Amplitude;
		float Kx;
		float Ky;
		float Omega;
		float Phase;
	};
	const float Swell = Sea.MaxAmplitudeCm;
	const FSeaWave Waves[] = {
		{ Swell * 2.8f, 0.00039f, 0.00008f, 0.46f, 0.3f },
		{ Swell * 1.4f, -0.00016f, 0.00052f, 0.62f, 1.4f },
		{ Swell * 0.85f, 0.00071f, 0.00022f, 0.88f, 0.8f },
		{ Swell * 0.45f, -0.00028f, 0.00084f, 1.12f, 2.1f },
		{ Sea.MinAmplitudeCm * 3.2f, 0.00058f, -0.00047f, 0.77f, 1.6f }
	};
	const float RimCm = 185000.f;
	const float EdgeCm = 220000.f;
	for (int32 Index = 0; Index < VisualSeaXY.Num(); ++Index)
	{
		const float X = VisualSeaXY[Index].X;
		const float Y = VisualSeaXY[Index].Y;
		const float WorldX = Center.X + X;
		const float WorldY = Center.Y + Y;
		const float Radius = FMath::Sqrt(X * X + Y * Y);
		const float Rim = FMath::Clamp((Radius - RimCm) / (EdgeCm - RimCm), 0.f, 1.f);
		const float Fade = 1.f - (Rim * Rim * (3.f - 2.f * Rim));
		float Height = 0.f;
		float SlopeX = 0.f;
		float SlopeY = 0.f;
		for (const FSeaWave& Wave : Waves)
		{
			const float Angle = WorldX * Wave.Kx + WorldY * Wave.Ky + Time * Wave.Omega + Wave.Phase;
			const float Sine = FMath::Sin(Angle);
			const float Cosine = FMath::Cos(Angle);
			Height += Wave.Amplitude * Sine;
			SlopeX += Wave.Amplitude * Wave.Kx * Cosine;
			SlopeY += Wave.Amplitude * Wave.Ky * Cosine;
		}
		Height *= Fade;
		SlopeX *= Fade;
		SlopeY *= Fade;
		// Shading only. These slopes are not added to the height, so swell shape and speed stay put.
		const FSeaWave Ripples[] = {
			{ Sea.MinAmplitudeCm * 1.6f, 0.00022f, 0.00055f, 0.54f, 0.6f },
			{ Sea.MinAmplitudeCm * 1.05f, -0.00041f, 0.00017f, 0.81f, 2.0f }
		};
		for (const FSeaWave& Ripple : Ripples)
		{
			const float Angle = WorldX * Ripple.Kx + WorldY * Ripple.Ky + Time * Ripple.Omega + Ripple.Phase;
			const float Cosine = FMath::Cos(Angle);
			SlopeX += Ripple.Amplitude * Ripple.Kx * Cosine * Fade;
			SlopeY += Ripple.Amplitude * Ripple.Ky * Cosine * Fade;
		}
		VisualSeaVertices[Index] = FVector(X, Y, Height);
		VisualSeaUV[Index] = FVector2D(WorldX * 0.00005f, WorldY * 0.00005f);
		const float Shade = 1.65f;
		VisualSeaNormals[Index] = FVector(-SlopeX * Shade, -SlopeY * Shade, 1.f).GetSafeNormal();
		const float Crest = FMath::Clamp(Height / FMath::Max(Swell * 2.4f, 1.f), 0.f, 1.f);
		const float Facing = FMath::Clamp(0.5f + SlopeX * 0.004f + SlopeY * 0.003f, 0.f, 1.f);
		VisualSeaColors[Index] = FColor(
			static_cast<uint8>(FMath::Clamp(4.f + Crest * 160.f + Facing * 24.f, 0.f, 255.f)),
			static_cast<uint8>(FMath::Clamp(18.f + Crest * 154.f + Facing * 32.f, 0.f, 255.f)),
			static_cast<uint8>(FMath::Clamp(30.f + Crest * 136.f + Facing * 28.f, 0.f, 255.f)));
	}
	if (!VisualSeaMesh->GetProcMeshSection(0))
	{
		VisualSeaMesh->CreateMeshSection(0, VisualSeaVertices, VisualSeaTriangles, VisualSeaNormals, VisualSeaUV, VisualSeaColors, TArray<FProcMeshTangent>(), false);
	}
	else
	{
		VisualSeaMesh->UpdateMeshSection(0, VisualSeaVertices, VisualSeaNormals, VisualSeaUV, VisualSeaColors, TArray<FProcMeshTangent>());
	}
}
