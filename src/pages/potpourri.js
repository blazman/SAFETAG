import React from "react"
import PropTypes from "prop-types"
import { Link, graphql } from "gatsby"
import styled from "styled-components"

import GlobalLayout from "../components/layouts/global-layout"
import SEO from "../components/seo"
import { themeVal } from "../styles/utils/general"
import { glsp } from "../styles/utils/theme-values"
import media from "../styles/utils/media-queries"

import Button from "../styles/button/button"
import {
  Inpage,
  InpageHeader,
  InpageHeaderInner,
  InpageHeadline,
  InpageBody,
  InpageBodyInner,
} from "../styles/inpage"
import Heading, { Subheading } from "../styles/type/heading"
import MoreLink from "../styles/button/more-link"
import Card, { CardHeader, CardHeading, CardList } from "../styles/card"

import LogoSymbolWhite from "../../static/assets/logo/SafetagSymbolWhiteBETA.svg"

const HomepageHeader = styled(InpageHeader)`
  background-color: ${themeVal("color.primary")};
  color: ${themeVal("color.surface")};
  position: relative;
  ${MoreLink} {
    color: ${themeVal("color.surface")};
    padding-bottom: ${glsp()};
    border-bottom: 1px solid ${themeVal("color.surface")};
  }
  ${media.mediumUp`
    padding-bottom: ${glsp(6)};
    &:after {
      content: url(${LogoSymbolWhite});
      position: absolute;
      bottom: 20%;
      right: 10%;
      opacity: 0.125;
      transform: scale(1.75);
    }
  `}
`

const HomepageHeaderInner = styled(InpageHeaderInner)`
  text-align: justify;
  ${media.mediumUp`
    padding: 6rem 1rem;
    padding-right: 40vw;
  `}
  ${media.largeUp`
    padding-right: 40rem;
  `}
`

const HomepageTitle = styled(Heading)`
  border-top: 2px solid ${themeVal("color.surface")};
  padding-top: ${glsp()};
`

const HomeCardList = styled(CardList)`
  margin: ${glsp(4)} 0;
`

const ContactButton = styled(Button)`
  font-size: 1.5rem;
  padding: 1rem;
  margin-top: 1rem;
`

function IndexPage() {

  return (
    <GlobalLayout>
      <SEO title="Safetag" />
      <Inpage>
        <HomepageHeader>
          <HomepageHeaderInner>
            <InpageHeadline>
              <HomepageTitle size="jumbo" variation="white">
                An Eclectic page of styles!
              </HomepageTitle>
            </InpageHeadline>
            <p>
              This is some text inside of InpageHadline
            </p>
          </HomepageHeaderInner>
        </HomepageHeader>
        <InpageBody>
          <InpageBodyInner>
            <Heading id="about" size="jumbo" variation="primary" withDeco>
              Section variation Primary withDeco
            </Heading>
            <p>
              Some Paragraph text
            </p>
          </InpageBodyInner>
        </InpageBody>

        <InpageBody variation="blue">
          <InpageBodyInner>
            <Heading id="recent-updates" size="jumbo" variation="primary" withDeco>
              Inpagebody variation blue
            </Heading>
            <p>
                Some paragraph text
            </p>
           
          </InpageBodyInner>
        </InpageBody>

        <InpageBody>
          <InpageBodyInner>

            <Heading id="allMethods" size="jumbo" variation="primary" withDeco>
              Another section
            </Heading>
            <Subheading>with a Subheading</Subheading>
            <HomeCardList>
                <Card border="primary" withHover>
                    <CardHeader>
                        <CardHeading variation="primary" withDeco>
                            What a cool card!
                        </CardHeading>
                    </CardHeader>
                    <p>Great test in a card right? Too bad there&apos;s only one of me</p>

                </Card>
            </HomeCardList>
            
            

          </InpageBodyInner>
        </InpageBody>

        <InpageBody variation="blue">
          <InpageBodyInner>
            <Heading id="license" size="jumbo" variation="primary" withDeco>
              License
            </Heading>
            <p>
              SAFETAG resources are available under a <a
              href="https://creativecommons.org/licenses/by-sa/3.0/">Creative
              Commons Attribution-ShareAlike (CC BY-SA 3.0) License</a>.
            </p>
            <p>
              Check out the <Link to="/credits/">Credits and Licensing
              </Link> page for content attribution and a usage guide to
              referring to the &quot;SAFETAG&quot; wordmark.

            </p>
            <p>
            </p>
          </InpageBodyInner>
        </InpageBody>

        <InpageBody>
          <InpageBodyInner>
            <Heading id="license" size="jumbo" variation="primary" withDeco>
              Get in touch
            </Heading>
            <ContactButton
                variation="primary-raised-light"
                to="#"
                onClick={(e) => {
                  window.location = "mailto:info@SAFETAG.org";
                  e.preventDefault();
                }}
                as={Link}>
              info@SAFETAG.org
            </ContactButton>
            <p>
              We have a global network of auditors trained in the SAFETAG
              framework available for independent work with small NGOs.
            </p>
            <p>
              For updates or suggestions for the framework, <a
              href="https://github.com/SAFETAG/SAFETAG/issues">submit an
              issue</a>.
            </p>

          </InpageBodyInner>
        </InpageBody>

      </Inpage>
    </GlobalLayout>
  )
}

IndexPage.propTypes = {
  data: PropTypes.array,
}

export default IndexPage

/*
      filter: {
        relativeDirectory: { eq: "methods" }
        internal: { mediaType: { eq: "text/markdown" } }
      }
*/

export const query = graphql`
  query {
    posts: allMarkdownRemark(
      sort: { fields: [frontmatter___date],  order: DESC },
      limit: 5,
      filter: {fileAbsolutePath: {regex: "/posts/"}}
    ) {
      edges {
        node {
          fields {
            slug
          }
          frontmatter {
            title
            date(formatString: "MMMM Do, YYYY")
          }
        }
      }
    }
    methods: allMarkdownRemark(
      sort: { fields: [frontmatter___position],  },
      filter: {fileAbsolutePath: {regex: "/methods/"}}
    ) {
      edges {
        node {
          fields {
            slug
          }
          frontmatter {
            title
            position
            method_icon
            summary
          }
        }
      }
    }
  }
`
