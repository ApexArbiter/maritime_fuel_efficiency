#include "MaritimeGameMode.h"

#include "BuoyancySubsystem.h"
#include "Engine/Engine.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "FleetCameraPawn.h"
#include "FleetEnvironment.h"
#include "FleetHUD.h"
#include "FleetShip.h"
#include "GameFramework/WorldSettings.h"
#include "GeoReferencingSystem.h"
#include "GerstnerWaterWaves.h"
#include "Materials/MaterialInstanceDynamic.h"
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

void AMaritimeGameMode::InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage)
{
	bFleetDemo = !FParse::Param(FCommandLine::Get(), TEXT("WaterTest"));
	if (bFleetDemo)
	{
		DefaultPawnClass = AFleetCameraPawn::StaticClass();
		HUDClass = AFleetHUD::StaticClass();
	}
	Super::InitGame(MapName, Options, ErrorMessage);
}

void AMaritimeGameMode::BeginPlay()
{
	Super::BeginPlay();

	if (AWorldSettings* Settings = GetWorld()->GetWorldSettings())
	{
		Settings->bEnableWorldBoundsChecks = false;
	}

	if (bFleetDemo && GEngine)
	{
		// The map asks for more tiles than the Linux cap. Restoring that density lets the Gerstner waves read.
		GEngine->Exec(GetWorld(), TEXT("r.Water.WaterMesh.MaxDimensionInTiles 512"));
	}

	BuildOcean();
	PinMapAndSun();

	if (UBuoyancySubsystem* BuoyancySubsystem = GetWorld()->GetSubsystem<UBuoyancySubsystem>())
	{
		BuoyancySubsystem->SetEnabled(true);
	}

	if (bFleetDemo)
	{
		for (TActorIterator<AActor> It(GetWorld()); It; ++It)
		{
			if (It->GetClass()->GetName().Contains(TEXT("Landscape")))
			{
				// Keep the ground in the water-depth capture so Gerstner waves are not faded to zero.
				// It stays far below the hull. This does not change the Python draft or heave.
				FVector Location = It->GetActorLocation();
				Location.Z = -12000.f;
				It->SetActorLocation(Location);
				It->SetActorEnableCollision(false);
				UE_LOG(LogTemp, Display, TEXT("Landscape lowered to %.0f cm so the ocean depth capture can drive visual waves"), Location.Z);
			}
		}
		FActorSpawnParameters EnvParams;
		EnvParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AFleetEnvironment* Environment = GetWorld()->SpawnActor<AFleetEnvironment>(AFleetEnvironment::StaticClass(), FTransform::Identity, EnvParams);
		SpawnFleet();
		if (Environment)
		{
			for (TActorIterator<AFleetShip> ShipIt(GetWorld()); ShipIt; ++ShipIt)
			{
				Environment->AddTickPrerequisiteActor(*ShipIt);
			}
		}
		if (GEngine)
		{
			GEngine->Exec(GetWorld(), TEXT("DisableAllScreenMessages"));
		}
	}
	else
	{
		SpawnShipIfNeeded();
		GetWorld()->SpawnActor<AWaterInteractionTest>(AWaterInteractionTest::StaticClass(), FTransform::Identity);
	}
}

void AMaritimeGameMode::SpawnBeacon(const FVector& Location, const FLinearColor& Color, float HeightCm)
{
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (!Cube)
	{
		return;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	const FVector PoleLocation = FVector(Location.X, Location.Y, HeightCm * 0.5f);
	AStaticMeshActor* Mark = GetWorld()->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), FTransform(FRotator::ZeroRotator, PoleLocation), Params);
	if (!Mark || !Mark->GetStaticMeshComponent())
	{
		return;
	}

	Mark->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
	Mark->GetStaticMeshComponent()->SetStaticMesh(Cube);
	Mark->SetActorScale3D(FVector(2.4f, 2.4f, HeightCm / 100.f));
	Mark->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Mark->GetStaticMeshComponent()->SetCastShadow(false);
	if (Base)
	{
		UMaterialInstanceDynamic* Instance = UMaterialInstanceDynamic::Create(Base, Mark);
		Instance->SetVectorParameterValue(TEXT("Color"), Color);
		Mark->GetStaticMeshComponent()->SetMaterial(0, Instance);
	}

	AStaticMeshActor* Cap = GetWorld()->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), FTransform(FRotator::ZeroRotator, FVector(Location.X, Location.Y, HeightCm + 250.f)), Params);
	if (Cap && Cap->GetStaticMeshComponent())
	{
		Cap->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
		Cap->GetStaticMeshComponent()->SetStaticMesh(Cube);
		Cap->SetActorScale3D(FVector(8.f, 8.f, 2.f));
		Cap->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Cap->GetStaticMeshComponent()->SetCastShadow(false);
		if (Base)
		{
			UMaterialInstanceDynamic* Instance = UMaterialInstanceDynamic::Create(Base, Cap);
			Instance->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.98f, 0.9f, 0.35f));
			Cap->GetStaticMeshComponent()->SetMaterial(0, Instance);
		}
	}
}

void AMaritimeGameMode::SpawnRoute(const FVector& From, const FVector& To, const FLinearColor& Color)
{
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (!Cube)
	{
		return;
	}

	const FVector A(From.X, From.Y, 0.f);
	const FVector B(To.X, To.Y, 0.f);
	const float Length = FVector::Dist2D(A, B);
	const int32 Pads = FMath::Clamp(FMath::RoundToInt(Length / 5000.f), 2, 48);
	const float Yaw = FMath::RadiansToDegrees(FMath::Atan2(B.Y - A.Y, B.X - A.X));
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	for (int32 Index = 1; Index < Pads; ++Index)
	{
		const FVector Point = FMath::Lerp(A, B, float(Index) / float(Pads)) + FVector(0.f, 0.f, 60.f);
		AStaticMeshActor* Pad = GetWorld()->SpawnActor<AStaticMeshActor>(AStaticMeshActor::StaticClass(), FTransform(FRotator(0.f, Yaw, 0.f), Point), Params);
		if (!Pad || !Pad->GetStaticMeshComponent())
		{
			continue;
		}
		Pad->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
		Pad->GetStaticMeshComponent()->SetStaticMesh(Cube);
		Pad->SetActorScale3D(FVector(7.f, 1.4f, 0.35f));
		Pad->GetStaticMeshComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Pad->GetStaticMeshComponent()->SetCastShadow(false);
		if (Base)
		{
			UMaterialInstanceDynamic* Instance = UMaterialInstanceDynamic::Create(Base, Pad);
			Instance->SetVectorParameterValue(TEXT("Color"), Color);
			Pad->GetStaticMeshComponent()->SetMaterial(0, Instance);
		}
	}
}

void AMaritimeGameMode::SpawnFleet()
{
	struct FDeparture
	{
		EFleetShipType Type;
		FVector Start;
		FVector First;
		FVector Second;
	};

	// Side-by-side departures on similar headings so a short view shows all three hulls.
	const FDeparture Departures[] = {
		{ EFleetShipType::Container, FVector(0.f, 0.f, 0.f), FVector(52000.f, 9000.f, 0.f), FVector(120000.f, 22000.f, 0.f) },
		{ EFleetShipType::Tanker, FVector(-5000.f, 14000.f, 0.f), FVector(48000.f, 24000.f, 0.f), FVector(116000.f, 38000.f, 0.f) },
		{ EFleetShipType::Bulker, FVector(-9000.f, -14000.f, 0.f), FVector(44000.f, -4000.f, 0.f), FVector(112000.f, 6000.f, 0.f) }
	};

	for (const FDeparture& Departure : Departures)
	{
		const float Bearing = FMath::RadiansToDegrees(FMath::Atan2(Departure.First.Y - Departure.Start.Y, Departure.First.X - Departure.Start.X));
		const FTransform Transform(FRotator(0.f, Bearing + 8.f, 0.f), Departure.Start);
		AFleetShip* Ship = GetWorld()->SpawnActorDeferred<AFleetShip>(AFleetShip::StaticClass(), Transform, nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
		if (!Ship)
		{
			continue;
		}
		TArray<FVector> Route;
		Route.Add(Departure.First);
		Route.Add(Departure.Second);
		Ship->Configure(Departure.Type, Route, Bearing + 8.f, 450.f);
		Ship->FinishSpawning(Transform);
		const FLinearColor RouteColor = Departure.Type == EFleetShipType::Tanker
			? FLinearColor(0.85f, 0.28f, 0.2f)
			: (Departure.Type == EFleetShipType::Bulker ? FLinearColor(0.3f, 0.75f, 0.35f) : FLinearColor(0.25f, 0.55f, 1.f));
		SpawnRoute(Departure.Start, Departure.First, RouteColor);
		SpawnRoute(Departure.First, Departure.Second, RouteColor);
		SpawnBeacon(Departure.First, RouteColor, 2800.f);
		SpawnBeacon(Departure.Second, RouteColor, 6400.f);
	}

	UE_LOG(LogTemp, Display, TEXT("FLEET DEMO READY wind 8.0 m/s toward 30 deg, current 0.6 m/s toward 80 deg"));
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
