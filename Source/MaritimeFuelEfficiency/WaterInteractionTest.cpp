#include "WaterInteractionTest.h"

#include "BuoyancyComponent.h"
#include "BuoyancyTypes.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "ShipPawn.h"
#include "TimerManager.h"
#include "WaterBodyActor.h"
#include "WaterBodyComponent.h"
#include "WaterBodyTypes.h"

DEFINE_LOG_CATEGORY_STATIC(LogWaterTest, Log, All);

AWaterProbe::AWaterProbe()
{
	PrimaryActorTick.bCanEverTick = false;

	Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	SetRootComponent(Body);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeMesh.Succeeded())
	{
		Body->SetStaticMesh(CubeMesh.Object);
	}

	Body->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Body->SetCollisionProfileName(TEXT("PhysicsActor"));
	Body->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Overlap);
	Body->SetGenerateOverlapEvents(true);
	Body->SetEnableGravity(true);
	Body->SetLinearDamping(2.f);
	Body->SetSimulatePhysics(true);

	Buoyancy = CreateDefaultSubobject<UBuoyancyComponent>(TEXT("Buoyancy"));
	Buoyancy->bUseAsyncPath = false;
	Buoyancy->BuoyancyData.bCenterPontoonsOnCOM = false;
	Buoyancy->BuoyancyData.BuoyancyCoefficient = 1.f;
	Buoyancy->BuoyancyData.bApplyDragForcesInWater = false;
	Buoyancy->AddCustomPontoon(50.f, FVector::ZeroVector);
}

void AWaterProbe::SetupProbe(float InMassKg)
{
	MassKg = InMassKg;
}

void AWaterProbe::BeginPlay()
{
	if (Body)
	{
		Body->SetSimulatePhysics(false);
		Body->SetMassOverrideInKg(NAME_None, MassKg, true);
		Body->SetLinearDamping(2.f);
		Body->SetEnableGravity(true);
		Body->SetSimulatePhysics(true);
		Body->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Overlap);
		Body->SetGenerateOverlapEvents(true);
	}

	Super::BeginPlay();

	if (Buoyancy)
	{
		Buoyancy->bUseAsyncPath = false;
		Buoyancy->SetComponentTickEnabled(true);
		for (TActorIterator<AWaterBody> It(GetWorld()); It; ++It)
		{
			if (It->GetWaterBodyType() != EWaterBodyType::Ocean || !It->GetWaterBodyComponent())
			{
				continue;
			}
			Buoyancy->EnteredWaterBody(It->GetWaterBodyComponent());
			break;
		}
	}
}

AWaterInteractionTest::AWaterInteractionTest()
{
	PrimaryActorTick.bCanEverTick = false;
}

static AWaterProbe* SpawnProbe(UWorld* World, float MassKg, const FVector& Location)
{
	const FTransform Transform(FRotator::ZeroRotator, Location);
	AWaterProbe* Probe = World->SpawnActorDeferred<AWaterProbe>(AWaterProbe::StaticClass(), Transform, nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	if (Probe)
	{
		Probe->SetupProbe(MassKg);
		Probe->FinishSpawning(Transform);
	}
	return Probe;
}

void AWaterInteractionTest::BeginPlay()
{
	Super::BeginPlay();

	UWorld* World = GetWorld();
	Wood = SpawnProbe(World, 200.f, FVector(50000.f, 0.f, 0.f));
	Iron = SpawnProbe(World, 3000.f, FVector(70000.f, 0.f, 0.f));

	UE_LOG(LogWaterTest, Display, TEXT("Water test dropped a 200 kg cube at 500 m and a 3000 kg cube at 700 m"));

	World->GetTimerManager().SetTimer(WaveTimer, this, &AWaterInteractionTest::SampleWaves, 1.f, false);
	World->GetTimerManager().SetTimer(FinishTimer, this, &AWaterInteractionTest::FinishTest, 12.f, false);
}

void AWaterInteractionTest::SampleWaves()
{
	AWaterBody* Ocean = nullptr;
	for (TActorIterator<AWaterBody> It(GetWorld()); It; ++It)
	{
		if (It->GetWaterBodyType() == EWaterBodyType::Ocean)
		{
			Ocean = *It;
			break;
		}
	}

	if (!Ocean || !Ocean->GetWaterBodyComponent())
	{
		UE_LOG(LogWaterTest, Error, TEXT("Wave check failed: no ocean"));
		bWavesPassed = false;
		return;
	}

	const TArray<FVector> Samples = {
		FVector(0.f, 0.f, 0.f),
		FVector(10000.f, 0.f, 0.f),
		FVector(0.f, 20000.f, 0.f),
		FVector(50000.f, 0.f, 0.f),
		FVector(-30000.f, 40000.f, 0.f)
	};

	UWaterBodyComponent* Body = Ocean->GetWaterBodyComponent();
	const EWaterBodyQueryFlags Flags = EWaterBodyQueryFlags::ComputeLocation | EWaterBodyQueryFlags::IncludeWaves;
	float Lowest = TNumericLimits<float>::Max();
	float Highest = TNumericLimits<float>::Lowest();
	int32 Successes = 0;

	for (const FVector& Sample : Samples)
	{
		const TValueOrError<FWaterBodyQueryResult, EWaterBodyQueryError> Result = Body->TryQueryWaterInfoClosestToWorldLocation(Sample, Flags);
		if (Result.HasError())
		{
			UE_LOG(LogWaterTest, Warning, TEXT("Wave query failed at %s"), *Sample.ToString());
			continue;
		}

		const float Height = Result.GetValue().GetWaterSurfaceLocation().Z;
		Lowest = FMath::Min(Lowest, Height);
		Highest = FMath::Max(Highest, Height);
		++Successes;
		UE_LOG(LogWaterTest, Display, TEXT("Wave surface at %s is %.1f cm"), *Sample.ToString(), Height);
	}

	WaveSpanCm = (Successes == Samples.Num()) ? (Highest - Lowest) : 0.f;
	const bool bHeightsInRange = Lowest >= -2000.f && Highest <= 2000.f;
	bWavesPassed = Successes == Samples.Num() && bHeightsInRange && WaveSpanCm > 5.f;
	UE_LOG(LogWaterTest, Display, TEXT("Wave span %.1f cm, pass %s"), WaveSpanCm, bWavesPassed ? TEXT("yes") : TEXT("no"));
}

void AWaterInteractionTest::FinishTest()
{
	const float WoodZ = Wood ? Wood->GetActorLocation().Z : -100000.f;
	const float IronZ = Iron ? Iron->GetActorLocation().Z : 0.f;
	const FVector WoodVelocity = (Wood && Wood->GetBody()) ? Wood->GetBody()->GetPhysicsLinearVelocity() : FVector::ZeroVector;
	const FVector IronVelocity = (Iron && Iron->GetBody()) ? Iron->GetBody()->GetPhysicsLinearVelocity() : FVector::ZeroVector;

	TActorIterator<AShipPawn> ShipIt(GetWorld());
	AShipPawn* Ship = ShipIt ? *ShipIt : nullptr;

	const float ShipZ = Ship ? Ship->GetActorLocation().Z : 100000.f;
	const bool bShipSimulating = Ship && Ship->GetHull() && Ship->GetHull()->IsSimulatingPhysics();
	bool bShipWet = false;
	int32 WetPontoons = 0;
	if (Ship && Ship->GetBuoyancy())
	{
		bShipWet = Ship->GetBuoyancy()->IsOverlappingWaterBody() || Ship->GetBuoyancy()->IsInWaterBody();
		for (const FSphericalPontoon& Pontoon : Ship->GetBuoyancy()->BuoyancyData.Pontoons)
		{
			if (Pontoon.bIsInWater)
			{
				++WetPontoons;
			}
		}
		if (WetPontoons > 0)
		{
			bShipWet = true;
		}
	}

	const bool bWoodFloats = WoodZ >= -150.f && WoodZ <= 400.f;
	const bool bIronSinks = IronZ < -500.f;
	const bool bSeparated = (WoodZ - IronZ) >= 300.f;
	const bool bShipHeld = Ship && FMath::Abs(ShipZ) <= 150.f && !bShipSimulating;

	const bool bPass = bWavesPassed && bWoodFloats && bIronSinks && bSeparated && bShipHeld && bShipWet;

	UE_LOG(LogWaterTest, Display, TEXT("Wood %.1f cm, vertical speed %.1f cm/s"), WoodZ, WoodVelocity.Z);
	UE_LOG(LogWaterTest, Display, TEXT("Iron %.1f cm, vertical speed %.1f cm/s"), IronZ, IronVelocity.Z);
	UE_LOG(LogWaterTest, Display, TEXT("Ship %.1f cm, simulating %d, wet pontoons %d"), ShipZ, bShipSimulating ? 1 : 0, WetPontoons);
	UE_LOG(LogWaterTest, Display, TEXT("%s"), bPass ? TEXT("WATER TEST PASS") : TEXT("WATER TEST FAIL"));

	FPlatformMisc::RequestExit(false);
}
