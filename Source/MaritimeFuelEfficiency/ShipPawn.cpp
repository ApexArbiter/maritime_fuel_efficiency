#include "ShipPawn.h"

#include "BuoyancyComponent.h"
#include "BuoyancyTypes.h"
#include "Components/StaticMeshComponent.h"
#include "EngineUtils.h"
#include "SocketSubsystem.h"
#include "Sockets.h"
#include "UObject/ConstructorHelpers.h"
#include "WaterBodyActor.h"
#include "WaterBodyComponent.h"

AShipPawn::AShipPawn()
{
	PrimaryActorTick.bCanEverTick = false;

	Hull = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Hull"));
	SetRootComponent(Hull);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeMesh.Succeeded())
	{
		Hull->SetStaticMesh(CubeMesh.Object);
	}

	// Engine cube is 1 m. This scale is a 320 m by 58 m by 20 m hull.
	Hull->SetRelativeScale3D(FVector(320.f, 58.f, 20.f));
	Hull->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Hull->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	Hull->SetGenerateOverlapEvents(true);
	Hull->SetSimulatePhysics(false);

	Buoyancy = CreateDefaultSubobject<UBuoyancyComponent>(TEXT("Buoyancy"));
	Buoyancy->bUseAsyncPath = false;
	Buoyancy->BuoyancyData.bCenterPontoonsOnCOM = false;
	Buoyancy->BuoyancyData.BuoyancyCoefficient = 1.f;
	Buoyancy->BuoyancyData.bApplyDragForcesInWater = false;

	const float RadiusCm = 500.f;
	const float DraftCm = -600.f;
	Buoyancy->AddCustomPontoon(RadiusCm, FVector(14000.f, 0.f, DraftCm));
	Buoyancy->AddCustomPontoon(RadiusCm, FVector(0.f, 0.f, DraftCm));
	Buoyancy->AddCustomPontoon(RadiusCm, FVector(-14000.f, 0.f, DraftCm));
	Buoyancy->AddCustomPontoon(RadiusCm, FVector(0.f, -2000.f, DraftCm));
	Buoyancy->AddCustomPontoon(RadiusCm, FVector(0.f, 2000.f, DraftCm));
}

void AShipPawn::BeginPlay()
{
	Super::BeginPlay();

	Hull->SetSimulatePhysics(false);
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

	ISocketSubsystem* Sockets = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	if (Sockets)
	{
		BridgeSocket = Sockets->CreateSocket(NAME_DGram, TEXT("ShipBridge"), true);
		if (BridgeSocket)
		{
			TSharedRef<FInternetAddr> Address = Sockets->CreateInternetAddr();
			Address->SetAnyAddress();
			Address->SetPort(9000);
			if (BridgeSocket->Bind(*Address))
			{
				UE_LOG(LogTemp, Display, TEXT("ShipBridge listening on port 9000"));
			}
			else
			{
				UE_LOG(LogTemp, Warning, TEXT("ShipBridge could not bind port 9000"));
			}
		}
	}
}

void AShipPawn::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (BridgeSocket)
	{
		BridgeSocket->Close();
		ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(BridgeSocket);
		BridgeSocket = nullptr;
	}
	Super::EndPlay(EndPlayReason);
}
