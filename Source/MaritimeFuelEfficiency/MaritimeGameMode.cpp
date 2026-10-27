#include "MaritimeGameMode.h"

#include "BuoyancySubsystem.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/WorldSettings.h"
#include "GeoReferencingSystem.h"
#include "GerstnerWaterWaves.h"
#include "ShipPawn.h"
#include "SunPosition.h"
#include "WaterBodyOceanActor.h"
#include "WaterBodyOceanComponent.h"
#include "WaterInteractionTest.h"
#include "WaterZoneActor.h"

AMaritimeGameMode::AMaritimeGameMode()
{
	DefaultPawnClass = AShipPawn::StaticClass();
}

void AMaritimeGameMode::BeginPlay()
{
	Super::BeginPlay();

	if (AWorldSettings* Settings = GetWorld()->GetWorldSettings())
	{
		Settings->bEnableWorldBoundsChecks = false;
	}

	BuildOcean();
	PinMapAndSun();
	SpawnShipIfNeeded();

	if (UBuoyancySubsystem* BuoyancySubsystem = GetWorld()->GetSubsystem<UBuoyancySubsystem>())
	{
		BuoyancySubsystem->SetEnabled(true);
	}

	if (FParse::Param(FCommandLine::Get(), TEXT("WaterTest")))
	{
		GetWorld()->SpawnActor<AWaterInteractionTest>(AWaterInteractionTest::StaticClass(), FTransform::Identity);
	}
}

void AMaritimeGameMode::BuildOcean()
{
	UWorld* World = GetWorld();

	TActorIterator<AWaterZone> ZoneIt(World);
	AWaterZone* Zone = ZoneIt ? *ZoneIt : nullptr;
	if (!Zone)
	{
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Zone = World->SpawnActor<AWaterZone>(AWaterZone::StaticClass(), FTransform::Identity, Params);
	}
	if (Zone)
	{
		Zone->SetZoneExtent(FVector2D(1600000.f, 1600000.f));
	}

	TActorIterator<AWaterBodyOcean> OceanIt(World);
	AWaterBodyOcean* Ocean = OceanIt ? *OceanIt : nullptr;
	if (!Ocean)
	{
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Ocean = World->SpawnActor<AWaterBodyOcean>(AWaterBodyOcean::StaticClass(), FTransform::Identity, Params);
	}
	if (!Ocean)
	{
		UE_LOG(LogTemp, Error, TEXT("Ocean was not spawned"));
		return;
	}

	UGerstnerWaterWaves* Waves = NewObject<UGerstnerWaterWaves>(Ocean);
	UGerstnerWaterWaveGeneratorSimple* Generator = NewObject<UGerstnerWaterWaveGeneratorSimple>(Waves);
	Generator->NumWaves = 16;
	Generator->Seed = 0;
	Generator->Randomness = 0.f;
	Generator->MinWavelength = 2000.f;
	Generator->MaxWavelength = 15000.f;
	Generator->WavelengthFalloff = 2.f;
	Generator->MinAmplitude = 15.f;
	Generator->MaxAmplitude = 120.f;
	Generator->AmplitudeFalloff = 2.f;
	Generator->WindAngleDeg = 30.f;
	Generator->DirectionAngularSpreadDeg = 60.f;
	Generator->SmallWaveSteepness = 0.4f;
	Generator->LargeWaveSteepness = 0.2f;
	Generator->SteepnessFalloff = 1.f;
	Waves->GerstnerWaveGenerator = Generator;
	Waves->RecomputeWaves(false);
	Ocean->SetWaterWaves(Waves);

	if (UWaterBodyOceanComponent* OceanComponent = Cast<UWaterBodyOceanComponent>(Ocean->GetWaterBodyComponent()))
	{
		// Both the floater and the water volume must generate overlaps. A block response never notifies buoyancy.
		OceanComponent->SetGenerateOverlapEvents(true);
#if WITH_EDITOR
		OceanComponent->SetCollisionExtents(FVector(1600000.f, 1600000.f, 20000.f));
		OceanComponent->SetOceanExtent(FVector2D(1600000.f, 1600000.f));
#else
		FOnWaterBodyChangedParams Params;
		Params.bShapeOrPositionChanged = true;
		OceanComponent->UpdateAll(Params);
#endif
		Ocean->UpdateOverlaps(true);
		UE_LOG(LogTemp, Display, TEXT("Ocean collision parts %d, overlap events %d"),
			OceanComponent->GetCollisionComponents(false).Num(),
			OceanComponent->GetGenerateOverlapEvents() ? 1 : 0);
	}

	UE_LOG(LogTemp, Display, TEXT("Ocean ready, 16 km across, Gerstner waves %.2f-%.1f m, max height %.1f cm"),
		Generator->MinAmplitude / 100.f,
		Generator->MaxAmplitude / 100.f,
		Waves->GetMaxWaveHeight());
}

void AMaritimeGameMode::PinMapAndSun()
{
	UWorld* World = GetWorld();
	TActorIterator<AGeoReferencingSystem> GeoIt(World);
	AGeoReferencingSystem* Geo = GeoIt ? *GeoIt : nullptr;
	if (!Geo)
	{
		Geo = World->SpawnActor<AGeoReferencingSystem>(AGeoReferencingSystem::StaticClass(), FTransform::Identity);
	}
	if (Geo)
	{
		Geo->PlanetShape = EPlanetShape::FlatPlanet;
		Geo->bOriginLocationInProjectedCRS = false;
		Geo->OriginLatitude = 40.0;
		Geo->OriginLongitude = -40.0;
		Geo->OriginAltitude = 0.0;
		Geo->ApplySettings();
	}

	FSunPositionData Sun;
	USunPositionFunctionLibrary::GetSunPosition(40.f, -40.f, 0.f, false, 2026, 6, 21, 12, 0, 0, Sun);
	float Elevation = Sun.CorrectedElevation;
	if (Elevation > 90.f)
	{
		Elevation -= 180.f;
	}
	UE_LOG(LogTemp, Display, TEXT("Sun elevation %.1f deg, azimuth %.1f deg"), Elevation, Sun.Azimuth);
}

void AMaritimeGameMode::SpawnShipIfNeeded()
{
	TActorIterator<AShipPawn> Existing(GetWorld());
	if (Existing)
	{
		return;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	GetWorld()->SpawnActor<AShipPawn>(AShipPawn::StaticClass(), FTransform::Identity, Params);
}
