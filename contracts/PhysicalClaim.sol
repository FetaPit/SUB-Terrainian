// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title PhysicalClaim
/// @notice Soulbound (EIP-5192) proof-of-physical-ownership tokens.
///         One token per wallet per MBID. Non-transferable after mint.
///         Issued when a user scans and verifies a physical release
///         (vinyl, CD, cassette) via SUB-Terrainian's physical catalogue flow.
interface IERC5192 {
    /// @notice Emitted when a token is locked (made soulbound).
    event Locked(uint256 tokenId);
    /// @notice Emitted when a token is unlocked. Never emitted by this contract.
    event Unlocked(uint256 tokenId);
    /// @notice Returns true if the token is locked (soulbound).
    function locked(uint256 tokenId) external view returns (bool);
}

contract PhysicalClaim is ERC721, IERC5192, Ownable {

    uint256 private _nextTokenId;

    // tokenId → mbid
    mapping(uint256 => bytes32) public tokenMbid;

    // wallet → mbid → has claimed
    mapping(address => mapping(bytes32 => bool)) public hasClaimed;

    // mbid → list of claimants (for lookup)
    mapping(bytes32 => address[]) private _claimants;

    event PhysicalVerified(
        uint256 indexed tokenId,
        address indexed claimant,
        bytes32 indexed mbid
    );

    error AlreadyClaimed(address claimant, bytes32 mbid);
    error ZeroAddress();
    error SoulboundToken();

    constructor(address initialOwner)
        ERC721("SUB-Terrainian Physical Claim", "SUBPHYS")
        Ownable(initialOwner)
    {}

    // ─── Owner actions ────────────────────────────────────────────────────────

    /// @notice Issue a soulbound physical-ownership token to `claimant`.
    ///         Called by the backend after barcode + MusicBrainz verification.
    /// @param claimant  Wallet address of the physical owner
    /// @param mbid      MusicBrainz release ID packed as bytes32
    function claim(address claimant, bytes32 mbid) external onlyOwner {
        if (claimant == address(0)) revert ZeroAddress();
        if (hasClaimed[claimant][mbid]) revert AlreadyClaimed(claimant, mbid);

        uint256 tokenId = _nextTokenId++;
        hasClaimed[claimant][mbid] = true;
        tokenMbid[tokenId] = mbid;
        _claimants[mbid].push(claimant);

        _safeMint(claimant, tokenId);

        emit Locked(tokenId);
        emit PhysicalVerified(tokenId, claimant, mbid);
    }

    // ─── EIP-5192 — all tokens permanently locked ─────────────────────────────

    function locked(uint256 tokenId) external pure override returns (bool) {
        return true; // every token is permanently soulbound
    }

    // ─── Block all transfers (soulbound enforcement) ───────────────────────────

    function transferFrom(address, address, uint256) public pure override {
        revert SoulboundToken();
    }

    function safeTransferFrom(address, address, uint256, bytes memory) public pure override {
        revert SoulboundToken();
    }

    function approve(address, uint256) public pure override {
        revert SoulboundToken();
    }

    function setApprovalForAll(address, bool) public pure override {
        revert SoulboundToken();
    }

    // ─── Views ────────────────────────────────────────────────────────────────

    /// @notice All wallets that have claimed physical ownership of a release.
    function claimantsFor(bytes32 mbid) external view returns (address[] memory) {
        return _claimants[mbid];
    }

    /// @notice Number of physical claims issued for a release.
    function claimCount(bytes32 mbid) external view returns (uint256) {
        return _claimants[mbid].length;
    }

    // ─── ERC-165 ──────────────────────────────────────────────────────────────

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override
        returns (bool)
    {
        return
            interfaceId == type(IERC5192).interfaceId ||
            super.supportsInterface(interfaceId);
    }
}
