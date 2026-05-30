// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {MusicEdition} from "../MusicEdition.sol";
import {PhysicalClaim} from "../PhysicalClaim.sol";

/// @notice Deploy MusicEdition + PhysicalClaim to Base (mainnet or Sepolia).
///
/// Usage — testnet:
///   forge script contracts/script/Deploy.s.sol \
///     --rpc-url base_sepolia \
///     --broadcast \
///     --verify \
///     --etherscan-api-key $BASESCAN_API_KEY
///
/// Usage — mainnet (add --slow for safety):
///   forge script contracts/script/Deploy.s.sol \
///     --rpc-url base \
///     --broadcast \
///     --verify \
///     --etherscan-api-key $BASESCAN_API_KEY \
///     --slow
contract Deploy is Script {

    function run() external {
        address deployer = vm.envAddress("DEPLOYER_ADDRESS");

        vm.startBroadcast();

        MusicEdition musicEdition = new MusicEdition(deployer);
        PhysicalClaim physicalClaim = new PhysicalClaim(deployer);

        vm.stopBroadcast();

        console.log("MusicEdition deployed at:", address(musicEdition));
        console.log("PhysicalClaim deployed at:", address(physicalClaim));
        console.log("Owner:", deployer);

        // Write addresses to stdout for the manifest_bridge to pick up
        console.log("MUSIC_EDITION_ADDRESS=%s", address(musicEdition));
        console.log("PHYSICAL_CLAIM_ADDRESS=%s", address(physicalClaim));
    }
}
