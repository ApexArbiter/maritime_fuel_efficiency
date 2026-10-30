#include "FleetShip.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "WaterBodyComponent.h"
#include "WaterBodyOceanActor.h"
#include "WaterBodyTypes.h"

DEFINE_LOG_CATEGORY_STATIC(LogFleet, Log, All);

const AFleetShip::FShipSpec& AFleetShip::SpecFor(EFleetShipType Type)
{
	// Class-typical full-load figures, not a named ship.
	static const FShipSpec Container = { TEXT("Container ship"), 300.f, 42.8f, 14.5f, 8.0f, 145000.f, 45700000.f, 22.5f };
	static const FShipSpec Tanker = { TEXT("Aframax tanker"), 245.f, 42.0f, 15.0f, 6.0f, 128000.f, 13500000.f, 15.0f };
	static const FShipSpec Bulker = { TEXT("Panamax bulker"), 225.f, 32.3f, 14.2f, 7.0f, 87000.f, 9800000.f, 14.5f };
	switch (Type)
	{
	case EFleetShipType::Tanker: return Tanker;
	case EFleetShipType::Bulker: return Bulker;
	default: return Container;
	}
}

AFleetShip::AFleetShip()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeFinder(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeFinder.Succeeded())
	{
		CubeMesh = CubeFinder.Object;
	}
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderFinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (CylinderFinder.Succeeded())
	{
		CylinderMesh = CylinderFinder.Object;
	}
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereFinder(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (SphereFinder.Succeeded())
	{
		SphereMesh = SphereFinder.Object;
	}
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MaterialFinder(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (MaterialFinder.Succeeded())
	{
		BaseMaterial = MaterialFinder.Object;
	}
}

void AFleetShip::Configure(EFleetShipType InType, const TArray<FVector>& InWaypoints, float InInitialYawDegrees, float InInitialSurgeCms)
{
	ShipType = InType;
	Waypoints = InWaypoints;
	YawDeg = InInitialYawDegrees;
	InitialYawDeg = InInitialYawDegrees;
	SurgeCms = InInitialSurgeCms;
	InitialSurgeCms = InInitialSurgeCms;
}

void AFleetShip::BeginPlay()
{
	Super::BeginPlay();

	const FShipSpec& Spec = SpecFor(ShipType);
	ShipName = Spec.Name;
	LengthCm = Spec.LengthM * 100.f;
	BeamCm = Spec.BeamM * 100.f;
	DraftCm = Spec.DraftM * 100.f;
	FreeboardCm = Spec.FreeboardM * 100.f;
	MassKg = Spec.DisplacementT * 1000.f;
	EnginePowerW = Spec.EnginePowerW;
	ServiceMs = Spec.ServiceKn * 0.514444f;
	WettedM2 = Spec.LengthM * (Spec.BeamM + 2.f * Spec.DraftM) * 0.85f;
	LateralAreaM2 = Spec.LengthM * Spec.FreeboardM;
	FrontalAreaM2 = Spec.BeamM * Spec.FreeboardM;

	BuildVisuals();
	SetActorRotation(FRotator(0.f, YawDeg, 0.f));
	RouteOrigin = GetActorLocation();
	bRouteOriginSet = true;

	UE_LOG(LogFleet, Display, TEXT("%s LOA %.0f m, beam %.1f m, draft %.1f m, displacement %.0f t, engine %.0f kW, service %.1f kn"),
		*ShipName, Spec.LengthM, Spec.BeamM, Spec.DraftM, Spec.DisplacementT, Spec.EnginePowerW / 1000.f, Spec.ServiceKn);
}

UStaticMeshComponent* AFleetShip::AddShape(UStaticMesh* Mesh, const FVector& LocationCm, const FRotator& Rotation, const FVector& Scale, const FLinearColor& Color, bool bCastShadow)
{
	if (!Mesh)
	{
		return nullptr;
	}

	const FName Name = MakeUniqueObjectName(this, UStaticMeshComponent::StaticClass(), TEXT("Part"));
	UStaticMeshComponent* Part = NewObject<UStaticMeshComponent>(this, Name);
	Part->SetStaticMesh(Mesh);
	Part->SetupAttachment(Root);
	Part->SetRelativeLocation(LocationCm);
	Part->SetRelativeRotation(Rotation);
	Part->SetRelativeScale3D(Scale);
	Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Part->SetCanEverAffectNavigation(false);
	Part->SetCastShadow(bCastShadow);
	Part->bReceivesDecals = false;
	if (UMaterialInstanceDynamic* Instance = MaterialFor(Color))
	{
		Part->SetMaterial(0, Instance);
	}
	Part->RegisterComponent();
	++BoxSerial;
	return Part;
}

void AFleetShip::AddBox(const FVector& LocationCm, const FVector& SizeCm, const FLinearColor& Color, bool bCastShadow)
{
	AddShape(CubeMesh, LocationCm, FRotator::ZeroRotator, SizeCm / 100.f, Color, bCastShadow);
}

UMaterialInstanceDynamic* AFleetShip::MaterialFor(const FLinearColor& Color)
{
	for (int32 Index = 0; Index < SharedColors.Num(); ++Index)
	{
		if (SharedColors[Index].Equals(Color))
		{
			return SharedMaterials[Index];
		}
	}
	if (!BaseMaterial)
	{
		return nullptr;
	}
	UMaterialInstanceDynamic* Instance = UMaterialInstanceDynamic::Create(BaseMaterial, this);
	Instance->SetVectorParameterValue(TEXT("Color"), Color);
	SharedColors.Add(Color);
	SharedMaterials.Add(Instance);
	return Instance;
}

void AFleetShip::BuildVisuals()
{
	const FLinearColor HullColor = ShipType == EFleetShipType::Tanker
		? FLinearColor(0.09f, 0.09f, 0.085f)
		: (ShipType == EFleetShipType::Bulker ? FLinearColor(0.13f, 0.18f, 0.13f) : FLinearColor(0.06f, 0.10f, 0.16f));
	const FLinearColor Antifoul(0.28f, 0.06f, 0.035f);
	const FLinearColor White(0.78f, 0.79f, 0.76f);
	const FLinearColor Window(0.04f, 0.07f, 0.10f);
	const FLinearColor Funnel = ShipType == EFleetShipType::Tanker
		? FLinearColor(0.55f, 0.08f, 0.06f)
		: (ShipType == EFleetShipType::Bulker ? FLinearColor(0.08f, 0.10f, 0.08f) : FLinearColor(0.10f, 0.22f, 0.45f));
	const float DeckZ = FreeboardCm;
	const FLinearColor DeckColor = ShipType == EFleetShipType::Tanker
		? FLinearColor(0.10f, 0.10f, 0.09f)
		: (ShipType == EFleetShipType::Bulker ? FLinearColor(0.16f, 0.22f, 0.14f) : FLinearColor(0.07f, 0.09f, 0.12f));

	// Local Z=0 is the simulation waterline. Python heave moves the actor; these meshes do not.
	// Below 0 is antifouling. Above 0 is topside paint. The boot stripe follows each station's beam.
	const int32 Slices = 24;
	for (int32 Slice = 0; Slice < Slices; ++Slice)
	{
		const float U0 = -0.50f + 1.0f * Slice / Slices;
		const float U1 = -0.50f + 1.0f * (Slice + 1) / Slices;
		const float U = (U0 + U1) * 0.5f;
		float BeamScale = 1.f;
		if (U < -0.28f)
		{
			BeamScale = FMath::Lerp(0.30f, 1.f, FMath::SmoothStep(-0.50f, -0.28f, U));
		}
		else if (U > 0.14f)
		{
			BeamScale = FMath::Lerp(1.f, 0.07f, FMath::SmoothStep(0.14f, 0.50f, U));
		}
		float KeelScale = 1.f;
		if (U < -0.32f)
		{
			KeelScale = FMath::Lerp(0.38f, 1.f, FMath::SmoothStep(-0.50f, -0.32f, U));
		}
		else if (U > 0.18f)
		{
			KeelScale = FMath::Lerp(1.f, 0.16f, FMath::SmoothStep(0.18f, 0.50f, U));
		}
		const float DeckScale = 1.f + 0.34f * FMath::Max(FMath::SmoothStep(0.12f, 0.50f, U), FMath::SmoothStep(-0.18f, -0.50f, U));
		const float X0 = U0 * LengthCm;
		const float X1 = U1 * LengthCm;
		const float Bottom = -DraftCm * KeelScale;
		const float Top = FreeboardCm * DeckScale;
		const float MidX = (X0 + X1) * 0.5f;
		const float SizeX = FMath::Max(X1 - X0, 40.f);
		const float SizeY = BeamCm * BeamScale;
		const bool bShadow = Slice % 4 == 1;
		if (Bottom < -8.f)
		{
			AddBox(FVector(MidX, 0.f, Bottom * 0.5f), FVector(SizeX, SizeY, -Bottom), Antifoul, bShadow);
		}
		if (Top > 8.f)
		{
			AddBox(FVector(MidX, 0.f, Top * 0.5f), FVector(SizeX, SizeY * 0.992f, Top), HullColor, false);
		}
		AddBox(FVector(MidX, 0.f, 12.f), FVector(SizeX * 1.01f, SizeY * 1.045f, 70.f), White, false);
		if (Top > DeckZ * 0.45f)
		{
			AddBox(FVector(MidX, 0.f, Top - 14.f), FVector(SizeX * 1.008f, SizeY * 1.02f, 28.f), DeckColor, false);
		}
		if (BeamScale > 0.72f && U > -0.32f && U < 0.20f)
		{
			const float RailY = SizeY * 0.48f;
			const FVector RailSize(SizeX * 0.96f, 40.f, 110.f);
			AddBox(FVector(MidX, RailY, Top + 40.f), RailSize, HullColor, false);
			AddBox(FVector(MidX, -RailY, Top + 40.f), RailSize, HullColor, false);
		}
	}

	const float BilgeRadius = BeamCm * 0.11f;
	AddShape(CylinderMesh, FVector(-LengthCm * 0.02f, 0.f, -DraftCm + BilgeRadius * 0.35f), FRotator(-90.f, 0.f, 0.f), FVector(BilgeRadius / 50.f, BilgeRadius / 50.f, LengthCm * 0.42f / 100.f), Antifoul, false);
	AddShape(SphereMesh, FVector(LengthCm * 0.46f, 0.f, -DraftCm * 0.58f), FRotator::ZeroRotator, FVector(LengthCm * 0.07f / 100.f, BeamCm * 0.16f / 100.f, DraftCm * 0.28f / 100.f), Antifoul, false);
	AddBox(FVector(-LengthCm * 0.46f, 0.f, -DraftCm * 0.70f), FVector(LengthCm * 0.07f, BeamCm * 0.05f, DraftCm * 0.38f), Antifoul, false);
	const float PropDiameter = DraftCm * 0.62f;
	AddShape(CylinderMesh, FVector(-LengthCm * 0.49f, 0.f, -DraftCm * 0.55f), FRotator(-90.f, 0.f, 0.f), FVector(PropDiameter / 100.f, PropDiameter / 100.f, 0.55f), FLinearColor(0.12f, 0.12f, 0.11f), false);
	AddBox(FVector(-LengthCm * 0.495f, 0.f, -DraftCm * 0.42f), FVector(80.f, 70.f, DraftCm * 0.55f), FLinearColor(0.10f, 0.10f, 0.10f), false);

	const float HouseStern = -0.48f * LengthCm;
	const float HouseLen = LengthCm * (ShipType == EFleetShipType::Container ? 0.16f : 0.14f);
	const float HouseHeight = ShipType == EFleetShipType::Container ? 2400.f : (ShipType == EFleetShipType::Tanker ? 1600.f : 1500.f);
	const float HouseX = HouseStern + HouseLen * 0.5f;
	AddBox(FVector(HouseX, 0.f, DeckZ + HouseHeight * 0.5f), FVector(HouseLen, BeamCm * 0.72f, HouseHeight), White, true);
	AddBox(FVector(HouseX + HouseLen * 0.06f, 0.f, DeckZ + HouseHeight + 320.f), FVector(HouseLen * 0.48f, BeamCm * 0.42f, 640.f), FLinearColor(0.78f, 0.80f, 0.78f), true);
	AddBox(FVector(HouseX + HouseLen * 0.5f + 25.f, 0.f, DeckZ + HouseHeight * 0.72f), FVector(36.f, BeamCm * 0.64f, 140.f), Window, false);
	AddBox(FVector(HouseX + HouseLen * 0.5f + 25.f, 0.f, DeckZ + HouseHeight * 0.42f), FVector(36.f, BeamCm * 0.60f, 120.f), Window, false);
	AddShape(CylinderMesh, FVector(HouseX - HouseLen * 0.22f, BeamCm * 0.16f, DeckZ + HouseHeight + 700.f), FRotator::ZeroRotator, FVector(5.2f, 5.2f, 14.f), Funnel, true);
	AddShape(CylinderMesh, FVector(HouseX - HouseLen * 0.22f, BeamCm * 0.16f, DeckZ + HouseHeight + 1450.f), FRotator::ZeroRotator, FVector(6.2f, 6.2f, 2.2f), FLinearColor(0.08f, 0.08f, 0.08f), false);
	AddShape(CylinderMesh, FVector(HouseX + HouseLen * 0.15f, 0.f, DeckZ + HouseHeight + 900.f), FRotator::ZeroRotator, FVector(0.7f, 0.7f, 22.f), FLinearColor(0.75f, 0.75f, 0.72f), false);

	if (ShipType == EFleetShipType::Container)
	{
		const FLinearColor Boxes[] = {
			FLinearColor(0.75f, 0.12f, 0.10f),
			FLinearColor(0.08f, 0.24f, 0.58f),
			FLinearColor(0.90f, 0.74f, 0.12f),
			FLinearColor(0.10f, 0.42f, 0.20f),
			FLinearColor(0.88f, 0.88f, 0.86f),
			FLinearColor(0.85f, 0.40f, 0.08f)
		};
		const int32 Bays = 12;
		const int32 Rows = 5;
		const float CargoStern = -0.24f * LengthCm;
		const float CargoBow = 0.40f * LengthCm;
		const float BayLength = (CargoBow - CargoStern) / Bays;
		const float RowWidth = BeamCm * 0.88f / Rows;
		for (int32 Bay = 0; Bay < Bays; ++Bay)
		{
			for (int32 Row = 0; Row < Rows; ++Row)
			{
				const int32 Tiers = 4 + (Bay + Row * 2) % 4;
				const float Height = Tiers * 260.f;
				const float X = CargoStern + BayLength * (Bay + 0.5f);
				const float Y = -BeamCm * 0.44f + RowWidth * (Row + 0.5f);
				const FLinearColor Body = Boxes[(Bay + Row) % 6];
				const FLinearColor Cap = Boxes[(Bay * 2 + Row + 3) % 6];
				AddBox(FVector(X, Y, DeckZ + Height * 0.5f), FVector(BayLength * 0.90f, RowWidth * 0.88f, Height), Body, true);
				AddBox(FVector(X, Y, DeckZ + Height - 130.f), FVector(BayLength * 0.94f, RowWidth * 0.92f, 260.f), Cap, false);
			}
		}
	}
	else if (ShipType == EFleetShipType::Tanker)
	{
		const FLinearColor Pipe(0.45f, 0.46f, 0.44f);
		const FLinearColor DeckGear(0.16f, 0.16f, 0.15f);
		const float PipeLength = LengthCm * 0.58f;
		const float PipeX = LengthCm * 0.04f;
		AddBox(FVector(PipeX, 0.f, DeckZ + 80.f), FVector(PipeLength, 160.f, 50.f), FLinearColor(0.55f, 0.55f, 0.52f), false);
		AddShape(CylinderMesh, FVector(PipeX, BeamCm * 0.12f, DeckZ + 140.f), FRotator(-90.f, 0.f, 0.f), FVector(0.9f, 0.9f, PipeLength / 100.f), Pipe, true);
		AddShape(CylinderMesh, FVector(PipeX, -BeamCm * 0.12f, DeckZ + 140.f), FRotator(-90.f, 0.f, 0.f), FVector(0.9f, 0.9f, PipeLength / 100.f), Pipe, true);
		for (int32 Dome = 0; Dome < 6; ++Dome)
		{
			const float X = -LengthCm * 0.16f + Dome * LengthCm * 0.09f;
			AddShape(CylinderMesh, FVector(X, 0.f, DeckZ + 50.f), FRotator::ZeroRotator, FVector(7.5f, 5.5f, 0.7f), DeckGear, false);
		}
		AddBox(FVector(LengthCm * 0.02f, 0.f, DeckZ + 160.f), FVector(900.f, BeamCm * 0.42f, 220.f), FLinearColor(0.62f, 0.63f, 0.60f), true);
		for (int32 Riser = 0; Riser < 4; ++Riser)
		{
			const float Y = (Riser - 1.5f) * BeamCm * 0.10f;
			AddShape(CylinderMesh, FVector(LengthCm * 0.02f, Y, DeckZ + 280.f), FRotator::ZeroRotator, FVector(1.3f, 1.3f, 4.5f), Pipe, false);
		}
		AddBox(FVector(LengthCm * 0.40f, 0.f, DeckZ + 180.f), FVector(LengthCm * 0.12f, BeamCm * 0.70f, 360.f), White, true);
	}
	else
	{
		const int32 Holds = 7;
		const float CargoStern = -0.18f * LengthCm;
		const float CargoBow = 0.34f * LengthCm;
		const float Pitch = (CargoBow - CargoStern) / Holds;
		for (int32 Hold = 0; Hold < Holds; ++Hold)
		{
			const float X = CargoStern + Pitch * (Hold + 0.5f);
			AddBox(FVector(X, 0.f, DeckZ + 140.f), FVector(Pitch * 0.78f, BeamCm * 0.72f, 220.f), FLinearColor(0.22f, 0.16f, 0.10f), true);
			AddBox(FVector(X, 0.f, DeckZ + 280.f), FVector(Pitch * 0.70f, BeamCm * 0.64f, 90.f), FLinearColor(0.62f, 0.40f, 0.18f), false);
		}
		for (int32 Crane = 0; Crane < 4; ++Crane)
		{
			const float X = CargoStern + Pitch * (Crane * 1.6f + 0.5f);
			AddShape(CylinderMesh, FVector(X, 0.f, DeckZ + 900.f), FRotator::ZeroRotator, FVector(2.4f, 2.4f, 16.f), FLinearColor(0.72f, 0.55f, 0.16f), true);
			AddBox(FVector(X + 700.f, 0.f, DeckZ + 1750.f), FVector(1600.f, 140.f, 140.f), FLinearColor(0.78f, 0.60f, 0.18f), true);
		}
		AddBox(FVector(LengthCm * 0.40f, 0.f, DeckZ + 200.f), FVector(LengthCm * 0.12f, BeamCm * 0.74f, 400.f), White, true);
	}

	for (int32 Mark = 0; Mark < 3; ++Mark)
	{
		const float Depth = DraftCm * Mark / 2.f;
		AddBox(FVector(LengthCm * 0.455f, BeamCm * 0.17f, -Depth), FVector(30.f, 24.f, 180.f), White, false);
	}

	const FLinearColor Foam(0.55f, 0.68f, 0.70f);
	for (int32 Piece = 0; Piece < 10; ++Piece)
	{
		if (UStaticMeshComponent* Part = AddShape(CubeMesh, FVector(-LengthCm * 0.5f, 0.f, 12.f), FRotator::ZeroRotator, FVector(0.2f, 0.2f, 0.08f), Foam, false))
		{
			WakeParts.Add(Part);
		}
	}

	UE_LOG(LogFleet, Display, TEXT("WATERLINE %s LOA %.1f m, beam %.1f m, keel %.2f m, waterline 0.00 m, deck %.2f m, physics draft %.2f m, visual only"),
		*ShipName, LengthCm / 100.f, BeamCm / 100.f, -DraftCm / 100.f, FreeboardCm / 100.f, DraftCm / 100.f);
	UE_LOG(LogFleet, Display, TEXT("%s visual built from %d parts, no collision"), *ShipName, BoxSerial);
}

bool AFleetShip::SampleWater(const FVector& WorldLocation, float& OutSurfaceZ, FVector& OutVelocity) const
{
	OutSurfaceZ = 0.f;
	OutVelocity = FVector::ZeroVector;
	UWaterBodyComponent* Body = OceanBody.Get();
	if (!Body)
	{
		return false;
	}

	const EWaterBodyQueryFlags Flags = EWaterBodyQueryFlags::ComputeLocation | EWaterBodyQueryFlags::IncludeWaves | EWaterBodyQueryFlags::ComputeVelocity;
	const TValueOrError<FWaterBodyQueryResult, EWaterBodyQueryError> Result = Body->TryQueryWaterInfoClosestToWorldLocation(WorldLocation, Flags);
	if (Result.HasError())
	{
		return false;
	}

	OutSurfaceZ = Result.GetValue().GetWaterSurfaceLocation().Z;
	OutVelocity = Result.GetValue().GetVelocity();
	OutVelocity.Z = 0.f;
	return true;
}

float AFleetShip::WrapDegrees(float Degrees)
{
	while (Degrees > 180.f)
	{
		Degrees -= 360.f;
	}
	while (Degrees < -180.f)
	{
		Degrees += 360.f;
	}
	return Degrees;
}

void AFleetShip::UpdateWake()
{
	if (WakeParts.Num() < 10)
	{
		return;
	}
	const float SpeedMs = FMath::Max(0.f, SurgeCms) / 100.f;
	const float Amount = FMath::Clamp(SpeedMs / 5.5f, 0.f, 1.f);
	const bool bShow = Amount > 0.08f;
	for (int32 Side = 0; Side < 2; ++Side)
	{
		UStaticMeshComponent* Part = WakeParts[Side];
		const float Sign = Side == 0 ? 1.f : -1.f;
		Part->SetVisibility(bShow);
		Part->SetRelativeLocation(FVector(LengthCm * 0.46f, Sign * BeamCm * 0.22f, 18.f));
		Part->SetRelativeRotation(FRotator(0.f, Sign * 32.f, 0.f));
		Part->SetRelativeScale3D(FVector(8.f * Amount, 1.6f * Amount, 0.08f));
	}
	for (int32 Index = 0; Index < 8; ++Index)
	{
		UStaticMeshComponent* Part = WakeParts[Index + 2];
		const float Sign = (Index % 2 == 0) ? 1.f : -1.f;
		const float Fade = 1.f - (static_cast<float>(Index) / 9.f);
		const float Back = LengthCm * 0.47f + 120.f + Index * (260.f + SpeedMs * 35.f);
		Part->SetVisibility(bShow && Fade > 0.12f);
		Part->SetRelativeLocation(FVector(-Back, Sign * (BeamCm * 0.06f + Index * (48.f + SpeedMs * 6.f)), 6.f));
		Part->SetRelativeRotation(FRotator(0.f, Sign * (3.f + Index), 0.f));
		Part->SetRelativeScale3D(FVector((6.2f + Index * 0.15f) * Amount, (1.8f + Index * 0.22f) * Amount * Fade, 0.06f));
	}
}

void AFleetShip::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UpdateAutopilot(DeltaSeconds);
	UpdateWake();
}

void AFleetShip::ResetVoyage()
{
	WaypointIndex = 0;
	YawDeg = InitialYawDeg;
	SurgeCms = InitialSurgeCms;
	SwayCms = 0.f;
	YawRateRad = 0.f;
	HeaveCm = 0.f;
	HeaveVel = 0.f;
	PitchDeg = 0.f;
	PitchVel = 0.f;
	RollDeg = 0.f;
	RollVel = 0.f;
	RudderDeg = 0.f;
	SetActorLocation(FVector(RouteOrigin.X, RouteOrigin.Y, 0.f));
	SetActorRotation(FRotator(0.f, YawDeg, 0.f));
	SpeedKnots = (SurgeCms / 100.f) * 1.943844f;
	LeewayDeg = 0.f;
}

void AFleetShip::UpdateAutopilot(float DeltaSeconds)
{
	const float Dt = FMath::Min(DeltaSeconds, 0.05f);
	if (Waypoints.Num() == 0)
	{
		return;
	}

	if (!OceanBody.IsValid())
	{
		TActorIterator<AWaterBodyOcean> OceanIt(GetWorld());
		if (OceanIt)
		{
			OceanBody = OceanIt->GetWaterBodyComponent();
		}
	}

	if (WaypointIndex >= Waypoints.Num())
	{
		WaypointIndex = 0;
	}

	const FVector Location = GetActorLocation();
	FVector Target = Waypoints[WaypointIndex];
	Target.Z = 0.f;
	const FVector FlatLocation(Location.X, Location.Y, 0.f);
	if (WaypointIndex < Waypoints.Num() - 1 && FVector::Dist2D(FlatLocation, Target) < 8000.f)
	{
		WaypointIndex += 1;
		Target = Waypoints[WaypointIndex];
		UE_LOG(LogFleet, Display, TEXT("%s reached a mark, next waypoint %d"), *ShipName, WaypointIndex);
	}

	float RemainingCm = FVector::Dist2D(FlatLocation, Target);
	for (int32 Index = WaypointIndex; Index + 1 < Waypoints.Num(); ++Index)
	{
		RemainingCm += FVector::Dist2D(Waypoints[Index], Waypoints[Index + 1]);
	}
	DistanceRemainingM = RemainingCm / 100.f;

	const float DistM = FVector::Dist2D(FlatLocation, Target) / 100.f;
	DesiredMs = DistM < 220.f ? 3.5f : 6.0f;
	const float BearingDeg = FMath::RadiansToDegrees(FMath::Atan2(Target.Y - Location.Y, Target.X - Location.X));
	const float HeadingError = WrapDegrees(BearingDeg - YawDeg);
	if (Dt > KINDA_SMALL_NUMBER)
	{
		RudderDeg = FMath::Clamp(HeadingError * 1.15f, -35.f, 35.f);
	}
}

void AFleetShip::ApplyMotion(float DeltaSeconds, float InSurgeCms, float InSwayCms, float InYawRate, float InYawDeg, float InHeaveCm, float InPitchDeg, float InRollDeg, float InFuelTonnesPerHour)
{
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);
	if (Dt <= KINDA_SMALL_NUMBER)
	{
		return;
	}

	SurgeCms = InSurgeCms;
	SwayCms = InSwayCms;
	YawRateRad = InYawRate;
	YawDeg = WrapDegrees(InYawDeg);
	HeaveCm = InHeaveCm;
	PitchDeg = FMath::Clamp(InPitchDeg, -8.f, 8.f);
	RollDeg = FMath::Clamp(InRollDeg, -12.f, 12.f);
	FuelTonnesPerHour = InFuelTonnesPerHour;

	const float YawRad = FMath::DegreesToRadians(YawDeg);
	const FVector Forward(FMath::Cos(YawRad), FMath::Sin(YawRad), 0.f);
	const FVector Right(-Forward.Y, Forward.X, 0.f);
	FVector NextLocation = GetActorLocation() + (Forward * SurgeCms + Right * SwayCms) * Dt;
	NextLocation.Z = HeaveCm;
	SetActorLocation(NextLocation);
	SetActorRotation(FRotator(PitchDeg, YawDeg, RollDeg));

	SpeedKnots = (SurgeCms / 100.f) * 1.943844f;
	LeewayDeg = FMath::RadiansToDegrees(FMath::Atan2(SwayCms, FMath::Max(SurgeCms, 50.f)));
	const float HoursRemaining = (DistanceRemainingM / FMath::Max(SurgeCms / 100.f, 0.5f)) / 3600.f;
	FuelRemainingTonnes = FuelTonnesPerHour * HoursRemaining;
}
