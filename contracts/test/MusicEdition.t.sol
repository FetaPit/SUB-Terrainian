// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {MusicEdition} from "../MusicEdition.sol";

contract MusicEditionTest is Test {

    MusicEdition public edition;
    address       public owner  = address(0xA11CE);
    address       public buyer  = address(0xB0B);
    address       public artist = address(0xAB1);

    bytes32 constant MBID   = keccak256("3d4a6b2e-test-mbid-bauhaus");
    uint256 constant TOKEN   = uint256(MBID);
    uint256 constant MAX     = 200;
    uint96  constant ROYALTY = 500; // 5%
    string  constant URI     = "ipfs://QmTestCID";

    function setUp() public {
        vm.prank(owner);
        edition = new MusicEdition(owner);
    }

    // ─── createEdition ────────────────────────────────────────────────────────

    function test_createEdition_succeeds() public {
        vm.prank(owner);
        edition.createEdition(TOKEN, MBID, MAX, URI, artist, ROYALTY);

        (bytes32 mbid, uint256 max,,, uint96 bps) = edition.editions(TOKEN);
        assertEq(mbid, MBID);
        assertEq(max, MAX);
        assertEq(bps, ROYALTY);
        assertEq(edition.mbidToTokenId(MBID), TOKEN);
    }

    function test_createEdition_reverts_duplicate() public {
        vm.startPrank(owner);
        edition.createEdition(TOKEN, MBID, MAX, URI, artist, ROYALTY);

        vm.expectRevert(abi.encodeWithSelector(MusicEdition.EditionAlreadyExists.selector, MBID));
        edition.createEdition(TOKEN, MBID, MAX, URI, artist, ROYALTY);
        vm.stopPrank();
    }

    function test_createEdition_reverts_zeroSupply() public {
        vm.prank(owner);
        vm.expectRevert(MusicEdition.InvalidEditionSize.selector);
        edition.createEdition(TOKEN, MBID, 0, URI, artist, ROYALTY);
    }

    function test_createEdition_reverts_royaltyTooHigh() public {
        vm.prank(owner);
        vm.expectRevert(MusicEdition.InvalidRoyaltyBps.selector);
        edition.createEdition(TOKEN, MBID, MAX, URI, artist, 1001);
    }

    function test_createEdition_reverts_notOwner() public {
        vm.prank(buyer);
        vm.expectRevert();
        edition.createEdition(TOKEN, MBID, MAX, URI, artist, ROYALTY);
    }

    // ─── mint ─────────────────────────────────────────────────────────────────

    function test_mint_succeeds() public {
        vm.startPrank(owner);
        edition.createEdition(TOKEN, MBID, MAX, URI, artist, ROYALTY);
        edition.mint(TOKEN, buyer, 1);
        vm.stopPrank();

        assertEq(edition.balanceOf(buyer, TOKEN), 1);
        assertEq(edition.totalSupply(TOKEN), 1);
    }

    function test_mint_enforcesMaxSupply() public {
        vm.startPrank(owner);
        edition.createEdition(TOKEN, MBID, 2, URI, artist, ROYALTY);
        edition.mint(TOKEN, buyer, 2);

        vm.expectRevert(abi.encodeWithSelector(MusicEdition.EditionSoldOut.selector, TOKEN, 2));
        edition.mint(TOKEN, buyer, 1);
        vm.stopPrank();
    }

    function test_mint_reverts_unknownToken() public {
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(MusicEdition.EditionNotFound.selector, TOKEN));
        edition.mint(TOKEN, buyer, 1);
    }

    // ─── royaltyInfo ──────────────────────────────────────────────────────────

    function test_royaltyInfo() public {
        vm.prank(owner);
        edition.createEdition(TOKEN, MBID, MAX, URI, artist, ROYALTY);

        (address recv, uint256 amount) = edition.royaltyInfo(TOKEN, 10_000);
        assertEq(recv, artist);
        assertEq(amount, 500); // 5% of 10_000
    }

    // ─── uri ──────────────────────────────────────────────────────────────────

    function test_uri_returns_metadataUri() public {
        vm.prank(owner);
        edition.createEdition(TOKEN, MBID, MAX, URI, artist, ROYALTY);
        assertEq(edition.uri(TOKEN), URI);
    }

    function test_uri_reverts_unknown() public {
        vm.expectRevert(abi.encodeWithSelector(MusicEdition.EditionNotFound.selector, TOKEN));
        edition.uri(TOKEN);
    }

    // ─── supportsInterface ────────────────────────────────────────────────────

    function test_supportsInterface_ERC1155() public view {
        assertTrue(edition.supportsInterface(0xd9b67a26)); // ERC1155
    }

    function test_supportsInterface_ERC2981() public view {
        assertTrue(edition.supportsInterface(0x2a55205a)); // ERC2981
    }
}
