// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {PhysicalClaim} from "../PhysicalClaim.sol";

contract PhysicalClaimTest is Test {

    PhysicalClaim public phys;
    address public owner   = address(0xA11CE);
    address public alice   = address(0xA1);
    address public bob     = address(0xB0B);

    bytes32 constant MBID_A = keccak256("bauhaus-in-the-flat-field");
    bytes32 constant MBID_B = keccak256("joy-division-unknown-pleasures");

    function setUp() public {
        vm.prank(owner);
        phys = new PhysicalClaim(owner);
    }

    // ─── claim ────────────────────────────────────────────────────────────────

    function test_claim_succeeds() public {
        vm.prank(owner);
        phys.claim(alice, MBID_A);

        assertEq(phys.balanceOf(alice), 1);
        assertTrue(phys.hasClaimed(alice, MBID_A));
        assertEq(phys.tokenMbid(0), MBID_A);
    }

    function test_claim_reverts_duplicate() public {
        vm.startPrank(owner);
        phys.claim(alice, MBID_A);

        vm.expectRevert(abi.encodeWithSelector(PhysicalClaim.AlreadyClaimed.selector, alice, MBID_A));
        phys.claim(alice, MBID_A);
        vm.stopPrank();
    }

    function test_claim_different_mbids_same_wallet() public {
        vm.startPrank(owner);
        phys.claim(alice, MBID_A);
        phys.claim(alice, MBID_B);
        vm.stopPrank();

        assertEq(phys.balanceOf(alice), 2);
    }

    function test_claim_same_mbid_different_wallets() public {
        vm.startPrank(owner);
        phys.claim(alice, MBID_A);
        phys.claim(bob, MBID_A);
        vm.stopPrank();

        assertEq(phys.claimCount(MBID_A), 2);
    }

    function test_claim_reverts_notOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        phys.claim(alice, MBID_A);
    }

    // ─── soulbound enforcement ────────────────────────────────────────────────

    function test_locked_always_true() public {
        vm.prank(owner);
        phys.claim(alice, MBID_A);
        assertTrue(phys.locked(0));
    }

    function test_transferFrom_reverts() public {
        vm.prank(owner);
        phys.claim(alice, MBID_A);

        vm.prank(alice);
        vm.expectRevert(PhysicalClaim.SoulboundToken.selector);
        phys.transferFrom(alice, bob, 0);
    }

    function test_approve_reverts() public {
        vm.prank(owner);
        phys.claim(alice, MBID_A);

        vm.prank(alice);
        vm.expectRevert(PhysicalClaim.SoulboundToken.selector);
        phys.approve(bob, 0);
    }

    function test_setApprovalForAll_reverts() public {
        vm.prank(alice);
        vm.expectRevert(PhysicalClaim.SoulboundToken.selector);
        phys.setApprovalForAll(bob, true);
    }

    // ─── views ────────────────────────────────────────────────────────────────

    function test_claimantsFor() public {
        vm.startPrank(owner);
        phys.claim(alice, MBID_A);
        phys.claim(bob, MBID_A);
        vm.stopPrank();

        address[] memory list = phys.claimantsFor(MBID_A);
        assertEq(list.length, 2);
        assertEq(list[0], alice);
        assertEq(list[1], bob);
    }

    // ─── ERC-165 ──────────────────────────────────────────────────────────────

    function test_supportsInterface_ERC5192() public view {
        // IERC5192 interfaceId
        bytes4 id = type(PhysicalClaim).interfaceId;
        // locked(uint256) selector
        assertTrue(phys.supportsInterface(0xb45a3c0e));
    }

    function test_supportsInterface_ERC721() public view {
        assertTrue(phys.supportsInterface(0x80ac58cd));
    }
}
