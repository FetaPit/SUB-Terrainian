// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC1155} from "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
import {ERC1155Supply} from "@openzeppelin/contracts/token/ERC1155/extensions/ERC1155Supply.sol";
import {ERC2981} from "@openzeppelin/contracts/token/common/ERC2981.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title MusicEdition
/// @notice Limited-edition music NFTs on Base. Each token type maps to a
///         MusicBrainz release MBID. Edition size is fixed at creation.
///         EIP-2981 royalties enforced on every secondary sale.
contract MusicEdition is ERC1155, ERC1155Supply, ERC2981, Ownable {

    struct Edition {
        bytes32  mbid;         // MusicBrainz release ID (keccak256 not used — raw UUID bytes)
        uint256  maxSupply;    // edition ceiling, set once, never raised
        string   metadataUri;  // ipfs://CID pointing to EIP-1155 JSON
        address  royaltyRecipient;
        uint96   royaltyBps;   // basis points, e.g. 500 = 5%
    }

    // tokenId → edition data
    mapping(uint256 => Edition) public editions;

    // mbid → tokenId (reverse lookup)
    mapping(bytes32 => uint256) public mbidToTokenId;

    // tokenId → exists
    mapping(uint256 => bool) private _exists;

    event EditionCreated(
        uint256 indexed tokenId,
        bytes32 indexed mbid,
        uint256 maxSupply,
        string  metadataUri
    );

    event Minted(
        uint256 indexed tokenId,
        address indexed to,
        uint256 amount,
        uint256 newTotal
    );

    error EditionAlreadyExists(bytes32 mbid);
    error EditionNotFound(uint256 tokenId);
    error EditionSoldOut(uint256 tokenId, uint256 maxSupply);
    error InvalidEditionSize();
    error InvalidRoyaltyBps();
    error ZeroAddress();

    constructor(address initialOwner)
        ERC1155("")
        Ownable(initialOwner)
    {}

    // ─── Owner actions ────────────────────────────────────────────────────────

    /// @notice Register a new music edition. Can only be called once per MBID.
    /// @param tokenId       Caller-supplied uint256 (use mbid_to_token_id from manifest_bridge.py)
    /// @param mbid          MusicBrainz release UUID packed as bytes32
    /// @param maxSupply     Edition ceiling. Must be > 0. Cannot be raised later.
    /// @param metadataUri   IPFS URI for EIP-1155 metadata JSON
    /// @param royaltyRecip  Address that receives secondary sale royalties
    /// @param royaltyBps    Royalty in basis points (max 1000 = 10%)
    function createEdition(
        uint256 tokenId,
        bytes32 mbid,
        uint256 maxSupply,
        string  calldata metadataUri,
        address royaltyRecip,
        uint96  royaltyBps
    ) external onlyOwner {
        if (_exists[tokenId] || mbidToTokenId[mbid] != 0) {
            revert EditionAlreadyExists(mbid);
        }
        if (maxSupply == 0) revert InvalidEditionSize();
        if (royaltyBps > 1000) revert InvalidRoyaltyBps();
        if (royaltyRecip == address(0)) revert ZeroAddress();

        editions[tokenId] = Edition({
            mbid:             mbid,
            maxSupply:        maxSupply,
            metadataUri:      metadataUri,
            royaltyRecipient: royaltyRecip,
            royaltyBps:       royaltyBps
        });

        mbidToTokenId[mbid] = tokenId;
        _exists[tokenId] = true;

        _setTokenRoyalty(tokenId, royaltyRecip, royaltyBps);

        emit EditionCreated(tokenId, mbid, maxSupply, metadataUri);
    }

    /// @notice Mint `amount` copies of an edition to `to`.
    function mint(
        uint256 tokenId,
        address to,
        uint256 amount
    ) external onlyOwner {
        if (!_exists[tokenId]) revert EditionNotFound(tokenId);
        if (to == address(0)) revert ZeroAddress();

        uint256 current = totalSupply(tokenId);
        if (current + amount > editions[tokenId].maxSupply) {
            revert EditionSoldOut(tokenId, editions[tokenId].maxSupply);
        }

        _mint(to, tokenId, amount, "");

        emit Minted(tokenId, to, amount, current + amount);
    }

    /// @notice Batch mint multiple editions in one transaction.
    function mintBatch(
        address          to,
        uint256[] calldata tokenIds,
        uint256[] calldata amounts
    ) external onlyOwner {
        if (to == address(0)) revert ZeroAddress();
        for (uint256 i; i < tokenIds.length; ++i) {
            uint256 id = tokenIds[i];
            if (!_exists[id]) revert EditionNotFound(id);
            uint256 current = totalSupply(id);
            if (current + amounts[i] > editions[id].maxSupply) {
                revert EditionSoldOut(id, editions[id].maxSupply);
            }
        }
        _mintBatch(to, tokenIds, amounts, "");
    }

    // ─── Metadata ─────────────────────────────────────────────────────────────

    function uri(uint256 tokenId) public view override returns (string memory) {
        if (!_exists[tokenId]) revert EditionNotFound(tokenId);
        return editions[tokenId].metadataUri;
    }

    // ─── EIP-2981 ─────────────────────────────────────────────────────────────

    function royaltyInfo(uint256 tokenId, uint256 salePrice)
        public
        view
        override
        returns (address receiver, uint256 royaltyAmount)
    {
        Edition storage e = editions[tokenId];
        receiver = e.royaltyRecipient;
        royaltyAmount = (salePrice * e.royaltyBps) / 10_000;
    }

    // ─── Overrides required by Solidity ───────────────────────────────────────

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC1155, ERC2981)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }

    function _update(
        address from,
        address to,
        uint256[] memory ids,
        uint256[] memory values
    ) internal override(ERC1155, ERC1155Supply) {
        super._update(from, to, ids, values);
    }
}
